"""M5: who answers a photo that came by SMS: the model, or a person in the back end. Plain words.

A person answers (the case waits on the helper desk; the caller is told nothing) when ANY of these is true:
  sure   the reader is less sure than SMS_SURE_LINE
  bad    the reader could not read it (saw nothing, a stand-in) or it is under the old bad-photo line
  small  a picture is narrower than SMS_SMALL_W dots
  lost   not every photo that was sent came whole
  none   no photo came whole
"""
from typing import Any

from haqdaar.contracts import tunables
from haqdaar.photo import in_call


def needs_person(finding: dict[str, Any], info: dict[str, Any]) -> list[str]:
    """The reasons a person must answer, in plain words. Empty: the model answers."""
    why = []
    whole, sent = int(info.get("whole", 0)), int(info.get("sent", 0))
    widths = [int(w) for w in info.get("widths", [])]
    try:
        sure = float(finding.get("sure", 0.0) or 0.0)
    except (TypeError, ValueError):
        sure = 0.0
    if whole == 0:
        why.append("none")
    if whole < sent:
        why.append("lost")
    if widths and min(widths) < tunables.SMS_SMALL_W:
        why.append("small")
    if sure < tunables.SMS_SURE_LINE:
        why.append("sure")
    if in_call.is_bad(finding):
        why.append("bad")
    return why
