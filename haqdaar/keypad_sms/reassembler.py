"""
Reassembler and protocol decoder for keypad-originated SMS photo uploads.
Supports both binary SMS frames and text Base64 fallback frames with CRC-8 validation.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


def calculate_crc8(data: bytes | bytearray) -> int:
    """
    Calculate 8-bit CRC using polynomial x^8 + x^2 + x + 1 (0x07).
    Matches the client-side JavaScript implementation.
    """
    crc = 0x00
    for byte in data:
      crc ^= byte
      for _ in range(8):
        if crc & 0x80:
          crc = ((crc << 1) ^ 0x07) & 0xFF
        else:
          crc = (crc << 1) & 0xFF
    return crc


@dataclass
class SMSPacket:
  magic: str  # Always 'H'
  msg_id: int
  seq_num: int
  total_chunks: int
  payload: bytes
  crc8: int
  is_valid: bool


def parse_sms_packet(raw_message: Union[str, bytes]) -> Optional[SMSPacket]:
  """
  Parse an incoming SMS into an SMSPacket.
  Supports:
  1. Text Base64 format: H:<msg_id_hex>:<seq>/<total>:<payload_b64>:<crc8_hex>
  2. Binary frame format: [Magic: 1B 'H'][MsgID: 2B][Seq: 1B][Total: 1B][CRC8: 1B][Payload: NB]
  """
  if isinstance(raw_message, str):
    raw_str = raw_message.strip()
    if not raw_str.startswith("H:"):
      return None
    parts = raw_str.split(":")
    if len(parts) != 5:
      return None

    magic = parts[0]
    try:
      msg_id = int(parts[1], 16)
      seq_str, total_str = parts[2].split("/")
      seq_num = int(seq_str)
      total_chunks = int(total_str)
      payload = base64.b64decode(parts[3])
      expected_crc = int(parts[4], 16)
    except Exception:
      return None

    computed_crc = calculate_crc8(payload)
    is_valid = computed_crc == expected_crc

    return SMSPacket(
        magic=magic,
        msg_id=msg_id,
        seq_num=seq_num,
        total_chunks=total_chunks,
        payload=payload,
        crc8=expected_crc,
        is_valid=is_valid,
    )

  elif isinstance(raw_message, (bytes, bytearray)):
    if len(raw_message) < 7:
      return None
    if raw_message[0] != 0x48:  # 'H'
      return None

    magic = "H"
    msg_id = int.from_bytes(raw_message[1:3], byteorder="big")
    seq_num = int(raw_message[3])
    total_chunks = int(raw_message[4])
    expected_crc = int(raw_message[5])
    payload = bytes(raw_message[6:])

    computed_crc = calculate_crc8(payload)
    is_valid = computed_crc == expected_crc

    return SMSPacket(
        magic=magic,
        msg_id=msg_id,
        seq_num=seq_num,
        total_chunks=total_chunks,
        payload=payload,
        crc8=expected_crc,
        is_valid=is_valid,
    )

  return None


@dataclass
class ReassemblySession:
  sender_phone: str
  msg_id: int
  total_chunks: int
  chunks: Dict[int, bytes] = field(default_factory=dict)
  created_at: float = field(default_factory=time.time)
  updated_at: float = field(default_factory=time.time)

  def add_chunk(self, seq_num: int, payload: bytes) -> bool:
    """Add a validated chunk. Returns True if chunk was new."""
    self.updated_at = time.time()
    if seq_num in self.chunks:
      return False
    self.chunks[seq_num] = payload
    return True

  def is_complete(self) -> bool:
    return len(self.chunks) == self.total_chunks and all(
        i in self.chunks for i in range(1, self.total_chunks + 1)
    )

  def missing_chunks(self) -> List[int]:
    return [i for i in range(1, self.total_chunks + 1) if i not in self.chunks]

  def reassemble(self) -> bytes:
    """Reassemble ordered chunks into binary byte buffer."""
    if not self.is_complete():
      raise ValueError(f"Session incomplete. Missing: {self.missing_chunks()}")
    buffer = bytearray()
    for i in range(1, self.total_chunks + 1):
      buffer.extend(self.chunks[i])
    return bytes(buffer)

  def is_valid_jpeg(self) -> bool:
    """Check for standard JPEG Start of Image (SOI) and End of Image (EOI)."""
    try:
      data = self.reassemble()
      return len(data) >= 4 and data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    except Exception:
      return False

  def generate_ack_text(self) -> str:
    """Generate compact SMS response for the client."""
    if self.is_complete():
      return f"ACK {self.msg_id:04x} OK"
    missing = self.missing_chunks()
    missing_str = ",".join(str(m) for m in missing[:15])  # Cap at 15 for SMS
    return f"NACK {self.msg_id:04x} MISSING {missing_str}"


class SMSReassemblyManager:
  """Manages multiple sessions across different phone numbers and message IDs."""

  def __init__(self, storage_dir: Optional[Union[str, Path]] = None):
    self.sessions: Dict[Tuple[str, int], ReassemblySession] = {}
    self.storage_dir = Path(storage_dir) if storage_dir else None
    if self.storage_dir:
      self.storage_dir.mkdir(parents=True, exist_ok=True)

  def ingest_sms(
      self, sender_phone: str, raw_message: Union[str, bytes]
  ) -> Tuple[bool, str, Optional[bytes]]:
    """
    Ingest an SMS message.
    Returns: (is_success, ack_text, assembled_bytes_if_complete)
    """
    packet = parse_sms_packet(raw_message)
    if not packet:
      return (False, "ERR INVALID_PACKET", None)

    if not packet.is_valid:
      return (False, f"ERR CRC_FAIL {packet.msg_id:04x}:{packet.seq_num}", None)

    key = (sender_phone, packet.msg_id)
    if key not in self.sessions:
      self.sessions[key] = ReassemblySession(
          sender_phone=sender_phone,
          msg_id=packet.msg_id,
          total_chunks=packet.total_chunks,
      )

    session = self.sessions[key]
    session.add_chunk(packet.seq_num, packet.payload)

    ack_text = session.generate_ack_text()

    if session.is_complete():
      image_data = session.reassemble()
      if self.storage_dir:
        output_file = (
            self.storage_dir
            / f"{sender_phone.replace('+', '')}_{packet.msg_id:04x}.jpg"
        )
        output_file.write_bytes(image_data)
      return (True, ack_text, image_data)

    return (True, ack_text, None)
