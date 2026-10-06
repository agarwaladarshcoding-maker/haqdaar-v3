"""M1/M3: each photo's share of SMS parts, and the cap on photos. Plain words."""

from haqdaar.contracts import tunables


# One photo 20 parts, two photos 12 each, three or more 10 each (10 is the floor).
def share_parts(n_photos: int) -> int:
    if n_photos <= 1:
        return 20
    if n_photos == 2:
        return 12
    return 10


def max_photos() -> int:
    return max(1, int(tunables.SMS_MAX_PHOTOS))


def max_parts(n_photos: int) -> int:
    """Most parts a whole case of n photos may use (20 / 24 / 30 / 40 / 50)."""
    n = max(1, min(int(n_photos), max_photos()))
    return n * share_parts(n)
