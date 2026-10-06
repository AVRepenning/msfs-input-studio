"""Potential overlaps are advisory: simulator contexts and flags affect behavior."""
from collections import defaultdict


def binding_conflicts(profile):
    groups = defaultdict(list)
    for identity in profile.actions():
        for slot in ('Primary', 'Secondary'):
            ids = frozenset(value.strip() for _, value in profile.keys(*identity, slot))
            if ids:
                groups[identity[0]].append((identity, slot, ids))
    result = defaultdict(list)
    for entries in groups.values():
        # Index by input to avoid comparing every action with every other action.
        index = defaultdict(list)
        for number, entry in enumerate(entries):
            for key in entry[2]:
                index[key].append(number)
        checked = set()
        for positions in index.values():
            for i, left in enumerate(positions):
                for right in positions[i + 1:]:
                    pair = (min(left, right), max(left, right))
                    if pair in checked:
                        continue
                    checked.add(pair)
                    a, b = entries[left], entries[right]
                    if a[0] == b[0]:
                        continue
                    if a[2] == b[2] or a[2] < b[2] or b[2] < a[2]:
                        kind = 'Same input / chord' if a[2] == b[2] else 'Button also used inside a chord'
                        result[a[0]].append((b[0], a[1], b[1], kind))
                        result[b[0]].append((a[0], b[1], a[1], kind))
    return dict(result)
