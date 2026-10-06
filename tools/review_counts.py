"""tools/review_counts.py: how often a person agreed with the model, by picture width (from logs/review_labels.jsonl).

    .venv/bin/python -m tools.review_counts

The owner moves SMS_SURE_LINE and SMS_SMALL_W by hand from this table.
"""
from haqdaar.photo import review


def main() -> None:
    rows = review.counts()
    if not rows:
        print("no answered cases yet")
        return
    print("width  cases  agreed")
    for w in sorted(rows):
        c = rows[w]
        print(f"{w:5}  {c['n']:5}  {c['same']:4} ({100 * c['same'] // c['n']}%)")


if __name__ == "__main__":
    main()
