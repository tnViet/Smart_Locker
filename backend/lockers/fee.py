# Tinh phi, Thiet ke backend muc 1.5


def duration_minutes(occupied_at, now):
    seconds = (now - occupied_at).total_seconds()
    if seconds < 0:
        return 0
    return int(seconds // 60)


def compute_fee(duration_min, rule, source):
    if source == "LOCAL":
        return 0
    if duration_min <= rule.free_min:
        return 0
    over = duration_min - rule.free_min
    blocks = (over + rule.block_min - 1) // rule.block_min
    return blocks * rule.block_fee
