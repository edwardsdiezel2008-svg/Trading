import sys

sys.path.insert(0, ".")

from scripts.generate_sample_data import generate_ticks


def test_generate_ticks_returns_expected_columns_and_length():
    df = generate_ticks(start_price=100.0, n_ticks=500, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=1)
    assert list(df.columns) == ["timestamp", "price", "size"]
    assert len(df) == 500


def test_generate_ticks_price_never_drops_to_zero_or_below():
    # The generator floors price at 0.01 every tick regardless of regime -
    # a low enough start_price plus a run of trend_down/high_vol_chop could
    # otherwise walk the price negative, which no real instrument can do.
    df = generate_ticks(start_price=1.0, n_ticks=5000, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=99)
    assert df["price"].min() > 0


def test_generate_ticks_is_deterministic_for_the_same_seed():
    df1 = generate_ticks(start_price=100.0, n_ticks=500, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=42)
    df2 = generate_ticks(start_price=100.0, n_ticks=500, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=42)
    assert df1["price"].tolist() == df2["price"].tolist()
    assert df1["size"].tolist() == df2["size"].tolist()


def test_generate_ticks_different_seeds_produce_different_prices():
    df1 = generate_ticks(start_price=100.0, n_ticks=500, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=1)
    df2 = generate_ticks(start_price=100.0, n_ticks=500, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=2)
    assert df1["price"].tolist() != df2["price"].tolist()


def test_generate_ticks_timestamps_are_evenly_spaced_by_the_given_interval():
    df = generate_ticks(start_price=100.0, n_ticks=10, start_time="2026-01-01 00:00:00", seconds_between_ticks=30, seed=1)
    deltas = df["timestamp"].diff().dropna().unique()
    assert len(deltas) == 1
    assert deltas[0].total_seconds() == 30


def test_main_writes_both_sample_files(tmp_path, monkeypatch):
    import scripts.generate_sample_data as generate_sample_data

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(generate_sample_data, "OUT_DIR", "data/sample")
    small_df = generate_ticks(start_price=100.0, n_ticks=20, start_time="2026-01-01 00:00:00", seconds_between_ticks=15, seed=1)
    monkeypatch.setattr(generate_sample_data, "generate_ticks", lambda *a, **k: small_df)

    generate_sample_data.main()

    import os
    assert os.path.exists("data/sample/NASDAQ_AAPL_ticks.csv")
    assert os.path.exists("data/sample/ES_ticks.csv")

    import pandas as pd
    written = pd.read_csv("data/sample/NASDAQ_AAPL_ticks.csv")
    assert len(written) == 20
    assert list(written.columns) == ["timestamp", "price", "size"]
