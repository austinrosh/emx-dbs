from __future__ import annotations

from emx_dbs.gds_io import create_rectangle_seed_gds


def main() -> None:
    create_rectangle_seed_gds(
        "examples/generic_nport/seed.gds",
        "TOP",
        [
            ((-25, -5, 25, 5), 126, 0),
            ((-5, -20, 5, 20), 126, 0),
        ],
    )
    create_rectangle_seed_gds(
        "examples/broadside_transformer/seed.gds",
        "TOP",
        [
            ((-45, 5, 45, 15), 126, 0),
            ((-45, -15, 45, -5), 126, 0),
            ((-45, 5, 45, 15), 125, 0),
            ((-45, -15, 45, -5), 125, 0),
            ((-5, -5, 5, 5), 225, 0),
        ],
    )


if __name__ == "__main__":
    main()
