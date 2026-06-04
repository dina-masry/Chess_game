def clean_chess(df):
    # 2a — Parse time_increment → time_base, time_inc
    df[['time_base', 'time_inc']] = (
        df['time_increment'].str.split('+', expand=True).astype(int)
    )

    # 2b — Add rating_diff
    df['rating_diff'] = df['white_rating'] - df['black_rating']

    # 2c — Extract opening_family
    df['opening_family'] = (
        df['opening_fullname'].str.split(':').str[0].str.strip()
    )

    # 2d — Drop high-null column (~93.98% null)
    df = df.drop(columns=['opening_response'])

    # 2e — Flag short games
    df['is_suspicious'] = df['turns'] < 5   # 342 games

    # 2f — Validate
    assert df['rating_diff'].notna().all()
    assert df.duplicated().sum() == 0

    return df