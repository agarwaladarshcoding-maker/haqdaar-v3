import base64
from pathlib import Path
import pytest
from haqdaar.keypad_sms.reassembler import (
    SMSPacket,
    ReassemblySession,
    SMSReassemblyManager,
    calculate_crc8,
    parse_sms_packet,
)


def test_crc8_calculation():
    data = b"123456789"
    # CRC-8 (poly 0x07, init 0x00) for "123456789" is known standard
    crc = calculate_crc8(data)
    assert isinstance(crc, int)
    assert 0 <= crc <= 255
    # Verification with single byte
    assert calculate_crc8(b"\x00") == 0


def test_parse_text_base64_packet():
    payload = b"HELLO KEYPAD WORLD"
    crc = calculate_crc8(payload)
    b64_payload = base64.b64encode(payload).decode("ascii")

    # Format: H:<msg_id_hex>:<seq>/<total>:<payload_b64>:<crc8_hex>
    packet_str = f"H:1a2b:1/3:{b64_payload}:{crc:02x}"
    pkt = parse_sms_packet(packet_str)

    assert pkt is not None
    assert pkt.magic == "H"
    assert pkt.msg_id == 0x1A2B
    assert pkt.seq_num == 1
    assert pkt.total_chunks == 3
    assert pkt.payload == payload
    assert pkt.crc8 == crc
    assert pkt.is_valid is True


def test_parse_corrupt_packet():
    payload = b"CORRUPTED PAYLOAD"
    b64_payload = base64.b64encode(payload).decode("ascii")
    # Wrong CRC
    packet_str = f"H:0001:1/1:{b64_payload}:99"
    pkt = parse_sms_packet(packet_str)
    assert pkt is not None
    assert pkt.is_valid is False


def test_parse_binary_packet():
    payload = b"BINARY_PAYLOAD_CHUNK_DATA"
    crc = calculate_crc8(payload)
    msg_id = 0x04D2  # 1234
    seq = 2
    total = 5

    # Binary layout: [0x48 ('H')][MsgID 2B][Seq 1B][Total 1B][CRC 1B][Payload]
    raw = bytearray([0x48])
    raw.extend(msg_id.to_bytes(2, "big"))
    raw.append(seq)
    raw.append(total)
    raw.append(crc)
    raw.extend(payload)

    pkt = parse_sms_packet(bytes(raw))
    assert pkt is not None
    assert pkt.msg_id == 1234
    assert pkt.seq_num == 2
    assert pkt.total_chunks == 5
    assert pkt.payload == payload
    assert pkt.is_valid is True


def test_session_out_of_order_and_reassembly():
    fake_jpeg = b"\xff\xd8" + b"X" * 300 + b"\xff\xd9"
    chunk_size = 100
    chunks = [fake_jpeg[i:i + chunk_size] for i in range(0, len(fake_jpeg), chunk_size)]
    total = len(chunks)

    session = ReassemblySession(sender_phone="+919876543210", msg_id=0xAA11, total_chunks=total)

    # Ingest chunks out-of-order: chunk 2, then 4, then 1, then 3
    order = [1, 3, 0, 2] if total == 4 else list(reversed(range(total)))
    for idx in order:
        seq = idx + 1
        session.add_chunk(seq, chunks[idx])

    assert session.is_complete() is True
    assert session.missing_chunks() == []
    assembled = session.reassemble()
    assert assembled == fake_jpeg
    assert session.is_valid_jpeg() is True
    assert session.generate_ack_text() == "ACK aa11 OK"


def test_session_missing_chunks_nack():
    session = ReassemblySession(sender_phone="+919876543210", msg_id=0x55, total_chunks=4)
    session.add_chunk(1, b"chunk1")
    session.add_chunk(3, b"chunk3")

    assert session.is_complete() is False
    assert session.missing_chunks() == [2, 4]
    assert session.generate_ack_text() == "NACK 0055 MISSING 2,4"

    with pytest.raises(ValueError, match="Session incomplete"):
        session.reassemble()


def test_manager_end_to_end_flow(tmp_path: Path):
    manager = SMSReassemblyManager(storage_dir=tmp_path)
    phone = "+919999900000"
    msg_id = 0xBEEF

    # Synthetic tiny JPEG
    sample_image = b"\xff\xd8KEYPAD_IMAGE_CONTENT_SAMPLE\xff\xd9"
    chunk_data = [sample_image[:15], sample_image[15:]]

    # Ingest chunk 1
    c1 = chunk_data[0]
    pkt1 = f"H:{msg_id:04x}:1/2:{base64.b64encode(c1).decode()}:{calculate_crc8(c1):02x}"
    ok1, ack1, data1 = manager.ingest_sms(phone, pkt1)
    assert ok1 is True
    assert "MISSING 2" in ack1
    assert data1 is None

    # Ingest chunk 2
    c2 = chunk_data[1]
    pkt2 = f"H:{msg_id:04x}:2/2:{base64.b64encode(c2).decode()}:{calculate_crc8(c2):02x}"
    ok2, ack2, data2 = manager.ingest_sms(phone, pkt2)
    assert ok2 is True
    assert ack2 == "ACK beef OK"
    assert data2 == sample_image

    # Check file saved to disk
    expected_file = tmp_path / "919999900000_beef.jpg"
    assert expected_file.exists()
    assert expected_file.read_bytes() == sample_image
