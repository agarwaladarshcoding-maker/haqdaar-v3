# Multi-Step Prompts: Keypad-First Offline Photo-over-SMS System

Use these prompts sequentially with Claude, Antigravity, or Muse to implement, refine, and deploy the offline keypad-phone photo transmission system.

---

## PROMPT 1: Keypad-First Client UI & Hardware Emulation (<10 KB Footprint)

```markdown
You are building an ultra-compact, zero-internet web client tailored specifically for low-end keypad and feature phones (KaiOS, J2ME browsers, Opera Mini, and 4G feature phones like JioPhone).

### Constraints & Hardware Boundaries:
1. Screen Budget: 240x320 (QVGA) or 128x160 px display. High-contrast monochromatic or LCD palette with large bitmap typography.
2. Input Exclusivity: 100% of interaction MUST be driven by the keypad:
   - Numeric shortcuts: [0] Help/Info, [1] Capture, [2] Compress, [3] Slice, [4] Dispatch, [5] Inbound ACK, [6] Gateway Phone.
   - D-Pad navigation: Up/Down for menu cycling, Center/Enter for Select, Left/Right Softkeys for Options/Back.
   - Symbols: [*] for Back/Clear, [#] for SMS Action/Submit.
3. Touch Prevention: When rendered on a modern touchscreen or smartphone browser, block all direct touches inside the simulated screen viewport and display a "USE KEYPAD BELOW" prompt. Render a physical 12-key + D-pad + softkey button housing at the bottom.
4. Footprint: Single self-contained HTML file (CSS + JS inline) under 15 KB uncompressed. Zero external CDNs, fonts, or libraries.

### Requirements:
1. Implement the responsive retro-feature phone chassis and 240x320 LCD screen container.
2. Intercept keyboard events (`Digit0`-`Digit9`, `*`, `#`, `ArrowUp`, `ArrowDown`, `Enter`, `F1`, `F2`) and map them to menu actions.
3. Add a synthetic Nokia-style keypad beeper using the Web Audio API oscillator.
4. Output the complete, self-contained HTML file ready for local testing.
```

---

## PROMPT 2: Offline Canvas Compressor & 130-Byte SMS Packetizer

```markdown
You are adding the offline image compression and slicing engine to the keypad phone client. The user must be able to capture photos and prepare them for transmission across cellular SMS without mobile data or internet access.

### Technical Specifications:
1. Capture Pipeline:
   - Integrate `<input type="file" accept="image/*" capture="environment">` with fallback to a procedural leaf test pattern if the device camera API is inaccessible.
2. Downscale & Compress Engine:
   - Target resolution: 160x120 px (or 120x90 for low-bandwidth mode).
   - Compress to JPEG quality ~0.35 on an offscreen `<canvas>` to achieve a 5 KB to 8 KB payload.
3. Binary & Base64 Packet Framing Protocol:
   - Segment size: 96 bytes raw binary per packet (encodes to ~128 characters Base64).
   - Framing schema:
     `H:<msg_id_hex>:<seq>/<total>:<base64_payload>:<crc8_hex>`
     Example: `H:1a2b:01/42:aW1hZ2VkYXRh...:3c`
   - CRC-8 Polynomial: `x^8 + x^2 + x + 1` (`0x07`).
4. Dispatcher:
   - Generate standard `sms:<gateway_number>?body=<encoded_chunk>` URIs for sequential dispatch via cellular SMS.
   - Store packets in `localStorage` until server ACK is registered.

### Deliverables:
1. Provide the complete JavaScript compression, CRC-8, and chunking functions.
2. Add a status view showing payload reduction stats (e.g. `2.4 MB -> 6.1 KB (-99.7%)`).
```

---

## PROMPT 3: Backend Reassembly Engine & Missing Chunk Recovery

```markdown
Implement the Python backend service responsible for ingesting fragmented SMS packets, verifying data integrity, and reconstructing the JPEG photo.

### Technical Specifications:
1. Packet Ingestion (`haqdaar/keypad_sms/reassembler.py`):
   - Parse incoming SMS messages in both Text Base64 format (`H:<id>:<seq>/<total>:<payload>:<crc8>`) and 6-byte binary frames (`[0x48][MsgID:2B][Seq:1B][Total:1B][CRC:1B][Data]`).
   - Validate payload integrity against the CRC-8 byte. Drop corrupted packets and emit an error code.
2. Session Defragmentation:
   - Maintain active sessions keyed by `(sender_phone, msg_id)`.
   - Support out-of-order arrival and duplicate chunk deduplication.
   - Detect missing sequence numbers when chunk transmission stalls.
3. Feedback / Protocol ACK:
   - Complete: return `ACK <msg_id_hex> OK`.
   - Incomplete: return `NACK <msg_id_hex> MISSING <comma_separated_indices>` (e.g., `NACK 1a2b MISSING 3,7,12`).
4. Reassembly & Verification:
   - Reassemble the full byte buffer and verify standard JPEG headers (`0xFF 0xD8 ... 0xFF 0xD9`).
   - Save reconstructed photos to a designated storage directory with metadata.

### Deliverables:
1. Complete Python 3.11 implementation with type annotations and dataclasses.
2. Comprehensive `pytest` test suite covering out-of-order packets, CRC failures, NACK generation, and end-to-end byte-for-byte JPEG validation.
```

---

## PROMPT 4: Hardware GSM Modem, SMS Limits & Hybrid Survey Fallback

```markdown
Address real-world telecommunication constraints in India and rural environments (daily SIM SMS limits of ~100 messages, SMS pricing, carrier spam filtering).

### Objectives:
1. Physical GSM Modem / WebSMS Gateway:
   - Write a serial listener script using PySerial to poll a USB GSM modem (e.g. SIM800 / Huawei E3372) using AT commands (`AT+CMGF=1`, `AT+CMGL="REC UNREAD"`), feeding incoming SMS chunks into `SMSReassemblyManager`.
2. Cost & Quota Mitigation — Hybrid Diagnostic Survey:
   - Add a 1-SMS questionnaire mode to the keypad client:
     - 4 numeric questions: Crop Type [1-9], Affected Part [1-3], Symptom Color [1-5], Progression [1-4].
     - Encodes all diagnostic answers into a single 4-byte text SMS: `CROP:1:3:2:1`.
   - Provide an extreme-compression mode: sending a 1 KB 64x48 1-bit monochrome thumbnail (only 8-10 SMS) alongside the survey code.
3. Write end-to-end simulation scripts testing transmission over simulated packet loss (10% drop rate) and automated retransmission loops.
---

## PROMPT 5: Minimalist 1-Button Capture, Multi-Photo Preview & 3-Choice Review (Add/Send/Delete) with Frictionless SMS Dispatch

```markdown
You are designing the user interface and interaction flow for an ultra-simple, low-literacy feature phone web client (targeting rural farmers using KaiOS, JioPhone, and keypad devices).

### Core Design Philosophy:
Eliminate cognitive overload and technical intimidation. The user should never see complex file selectors, raw compression stats, packet framing, or debug telemetry. Every step must be self-explanatory with high visual hierarchy, bilingual support (English + Hindi), and unambiguous keypad shortcuts.

### Screen & State Flow Requirements:

1. Screen 1: Initial Idle State (Strictly ONE Action)
   - The screen must present ONLY ONE prominent action: "CAPTURE PHOTO" / "फोटो खींचें".
   - No configuration toggles, no gateway inputs, no secondary buttons.
   - Triggerable via physical [OK], center D-pad, Soft Left, or keypad digit [5].
   - When tapped or pressed, immediately activates the device camera (`<input type="file" accept="image/*" capture="environment">`) with a procedural test pattern fallback if hardware camera is blocked.

2. Screen 2: Photo Preview & 3-Choice Review (After Capture)
   - Immediately renders the captured photo preview thumbnail on the LCD display.
   - Multi-Photo Batching: If multiple photos are captured (up to 3 photos), display pagination counter (e.g., `PHOTO 1 OF 2`) with D-pad Left/Right navigation to browse between captured photos.
   - Presents exactly THREE clear, numbered options:
     - Option 1 [1]: "➕ ADD MORE" (और फोटो जोड़ें) — opens camera to capture an additional angle/symptom.
     - Option 2 [2]: "📤 SEND NOW" (भेजें) — commits the batch and triggers sending. (Also mapped to primary [OK], [#], and Soft Left).
     - Option 3 [3]: "🗑️ DELETE" (हटाएं) — removes the current previewed photo. If all photos are deleted, smoothly transitions back to Screen 1. (Also mapped to Soft Right and [*]).

3. Screen 3: Clean Sending & Loading State
   - Initiated when the user presses Send [2] / [OK].
   - Displays a clean, uncluttered loading experience:
     - Animated progress bar: `SENDING... [====>    ] 50%`
     - Simple subtext: `फोटो भेजी जा रही है...`
     - If multiple photos: `Photo 1 of 2` indicator.
   - STRICT PROHIBITION: Do NOT show raw packet framing (`H:1a2b:01/42...`), CRC-8 checksums, hex dumps, or raw byte counters on the user screen. All packet slicing and SMS dispatching (`sms:<gateway>?body=...`) happens silently in the background.

4. Screen 4: Clean Success Confirmation
   - Displays a prominent high-contrast checkmark `✔`.
   - Text: "SENT SUCCESSFULLY!" / "सफलतापूर्वक भेजा गया".
   - Brief reassurance: "Doctor / Expert will call or reply shortly."
   - Action prompt: "Press [OK] for New Photo" to reset back to Screen 1.
   - No lingering processing logs or heavy telemetry.

### Technical & Platform Constraints:
1. Form Factor & Styling: 240x320 px LCD retro palette (greenish `#8ca886` background with dark `#122013` pixel elements), monospace typography.
2. Dual-Mode Input: Full hardware keyboard event listener (`Digit1`, `Digit2`, `Digit3`, `Enter`, `SoftLeft`, `SoftRight`, `ArrowLeft`, `ArrowRight`, `*`, `#`) plus responsive on-screen keypad and clickable UI options for modern touchscreen browser testing.
3. Bundle Size: Entire implementation (HTML + CSS + JS) must remain fully self-contained in a single file under 20 KB with zero external dependencies.
```
