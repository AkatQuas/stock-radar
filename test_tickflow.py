import requests
from tickflow import TickFlow

# 使用免费服务（无需 API key）
tf = TickFlow.free()


# 查询单个日K线数据
def single():
    df = tf.klines.get("600000.SH", period="1d", count=500, adjust="forward", as_dataframe=True)
    print(df.tail())


# 查询标的信息
def batch():
    batch_df = tf.klines.batch(
        symbols=["600004.SH", "000002.SZ"],
        period="1d",
        count=10,
        as_dataframe=True,
        show_progress=True,
    )
    # dfs 是 dict[str, DataFrame]
    print(batch_df["600004.SH"].tail())


token = "8B3BF973-E32D-40B8-80AB-E22B3ED751E0"


def ztgc():
    url = "https://api.zhituapi.com/hs/pool/ztgc/{date}?token={token}"
    response = requests.get(url.format(date="2026-06-08", token=token))

    data = response.json()

    print(data)


def qsgc():
    url = "https://api.zhituapi.com/hs/pool/qsgc/{date}?token={token}"

    response = requests.get(url.format(date="2026-06-08", token=token))

    data = response.json()

    print(data)


if __name__ == "__main__":
    print("test_tickflow")
    # single()
    # batch()
    # ztgc()
    # qsgc()
