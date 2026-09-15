# RoboSense E1R：点群の受信・復号・表示

E1Rから届くUDPデータをPythonで読み取り、XYZ座標・intensity（反射強度）・各点の時刻を取り出すコードです。
点群の保存、Open3Dでの表示、自分の物体検出・SLAM処理への受け渡しに使えます。物体検出やSLAM自体は含みません。

```text
E1Rセンサー → Ethernet → PC / Jetson
                           ↓
                       UDPを受信
                           ↓
                  パケットを復号して点群に変換
                           ↓
                  フレーム単位でまとめる
                           ↓
                 保存 / 表示 / 自分の後処理
```

実機がない場合は、公開PCAP（通信を記録したファイル）で試せます。

## 1. 最初の準備

Python 3.10以上とGitを用意してください。基本機能の依存はNumPyとdpktです。
復号にROSやGPUは不要です。Open3D表示にはデスクトップ環境とOpenGLが必要です。

### コードを取得する

GitHubにアクセスできるアカウントで実行します（Privateリポジトリです）。

```bash
git clone https://github.com/yuki1125/robosense-e1r-decoder.git
cd robosense-e1r-decoder
```

すでにコードがある場合は、そのフォルダーでターミナルを開けば構いません。
以下のコマンドは、すべて **README.mdがあるフォルダー** で実行します。

### UbuntuでPython環境を作る

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[viewer,test]'
```

### Windows（PowerShell）でPython環境を作る

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[viewer,test]"
```

Windowsでは、以降の例の `python` を `.\.venv\Scripts\python.exe` に置き換えてください。
すでにこのプロジェクト用の `.venv` がある場合は、作り直す必要はありません。
表示もテストも不要なら、インストールは `python -m pip install -e .` だけで十分です。

## 2. 実機センサーを接続する

1. E1Rをメーカー指定の方法で給電し、EthernetでPCの有線LANへ接続します。
2. センサーのIPアドレスとサブネットマスクを、機器の設定・公式資料で確認します。
3. PCの有線LANに、センサーと通信できるIPアドレスを設定します。
4. センサーのUDP送信先を、受信するPCの有線LANのIPアドレスに設定します。送信先ポートも確認します。
5. PCのファイアウォールで、使用するPythonプログラムのUDP受信を許可します。

このPythonコードは **センサーやPCのネットワーク設定を変更しません**。設定方法・給電条件は機器の公式資料に従ってください。

同一サブネットの設定例（**E1Rの工場出荷値ではありません**）:

| 設定する場所 | 設定例 |
|---|---|
| センサーのIP | `192.168.1.200` |
| PCの有線LANのIP | `192.168.1.100` |
| 両方のサブネットマスク | `255.255.255.0` |
| センサーのUDP送信先IP | `192.168.1.100` |
| 点群用UDP送信先ポート（MSOP） | `6699` |
| IMU等のUDP送信先ポート（DIFOP） | `7788` |

実際の機器設定に合わせて変更してください。PCとセンサーに同じIPを設定しないでください。

## 3. 実機から点群を取得する

### まず受信できるか確認する

**ターミナルを1つ開き**、次を実行します。

```bash
python -m e1r_decoder.live --bind-ip 0.0.0.0 --msop-port 6699 --difop-port 7788 --debug 3
```

- `READY`：PC側で受信を開始できたという意味です。センサーからデータが届いた証明ではありません。
- パケット情報：有効な点群パケットを受信すると、最初の3個の情報を表示します。
- `Frame ... packets=... points=...`：点群がフレームとしてまとまったことを示します。
- 終了：**Ctrl+C**を押すと停止し、受信数・不正パケット数などを表示します。

`--bind-ip 0.0.0.0` は「PCのすべてのIPv4インターフェースで待ち受ける」という意味です。
ここにはセンサーのIPではなく、PC側のIPまたは `0.0.0.0` を指定します。
センサーに設定する送信先IPには、PCの実際の有線LANのIPを指定してください。
必要なら `--source-ip 192.168.1.200` のように受信元を限定できます。1プロセスにつき1センサーを想定しています。

### 点群を保存する

前のコマンドをCtrl+Cで止めてから実行します。

```bash
python -m e1r_decoder.live --output output/live --format both
```

1フレームごとに、`output/live/` へ保存します。

| ファイル | 中身 |
|---|---|
| `frame_000001.npz` | XYZ、intensity、各点の時刻など。NumPyから読めます |
| `frame_000001.pcd` | XYZ、intensity。点群ツール用のbinary PCD形式です |
| `frame_000001.json` | 時刻範囲、パケット数、不完全な理由など |
| `imu.jsonl` | DIFOPを受信した場合のraw IMU値 |

出力先は実行ごとに分けてください。同じ番号の点群ファイルは上書き、IMUは追記されます。
`--duration 10` を追加すると約10秒で終了します。

### Open3Dでリアルタイム表示する

受信中の `live` を止めてから実行します。

```bash
python -m e1r_decoder.viewer --bind-ip 0.0.0.0 --msop-port 6699
```

点群を受信するとウィンドウに表示します。マウスで視点を操作でき、ウィンドウを閉じるかCtrl+Cで終了します。
`--point-size 3` で点を大きくできます。ビューアは最新フレームを表示し、過去の点群を蓄積・保存しません。
**live、viewer、次のサンプルは同じUDPポートを使うため、どれか1つだけ起動してください。**

## 4. Pythonコードから点群を使うサンプル

以下をプロジェクト直下に **`receive_points.py`** という名前で保存してください。
センサーの接続・ネットワーク設定を済ませれば、このコードだけで受信からフレーム取得まで行えます。

```python
import numpy as np

from e1r_decoder.live import receive
from e1r_decoder.pipeline import Pipeline


def on_frame(frame):
    """点群が1フレーム分まとまるたびに呼ばれます。"""
    if not frame.complete:
        print(f"Frame {frame.frame_index}: partialのためスキップ {frame.reasons}")
        return

    points = frame.points
    xyz = np.column_stack([points["x"], points["y"], points["z"]])
    intensity = points["intensity"]
    timestamps = points["timestamp"]

    print(f"Frame {frame.frame_index}: {len(xyz)}点")
    print(f"  先頭の点 XYZ [m]: {xyz[0]}")
    print(f"  intensity: {intensity[0]}, timestamp [s]: {timestamps[0]:.6f}")

    # ここで自分の処理に渡します。以下は呼び出し方のイメージです。
    # detect_objects(xyz)
    # slam.update(xyz, timestamps)


def main():
    pipeline = Pipeline(on_frame=on_frame)
    try:
        receive(
            pipeline,
            bind_ip="0.0.0.0",  # PC側で待ち受けるIP
            msop_port=6699,      # 点群
            difop_port=7788,     # IMU等（この例では復号・集計のみ）
            on_ready=lambda: print("受信待機中。終了するにはCtrl+C", flush=True),
        )
    except KeyboardInterrupt:
        print("受信を終了します")
    finally:
        # 終了時だけ残りを取り出し、統計を表示します。
        # 残りのpartial frameにもon_frameが呼ばれます。
        print(pipeline.finish())


if __name__ == "__main__":
    main()
```

実行コマンド:

```bash
python receive_points.py
```

### frameとは？

センサーから届く小さなUDPパケットを、1回分の点群スキャンとしてまとめたものです。
今回の公開PCAPでは約0.1秒に1フレーム（約10 Hz）、通常288パケット・27,648点でした。
次のスキャンへの切り替わりをsequence番号から検出すると、直前のフレームが `on_frame` に渡されます。
固定288パケットで分割しているわけではありません。

`frame.complete` がfalseのものをpartial（不完全）と呼びます。受信開始直後・終了時・欠落などで発生します。
このサンプルはpartialを後処理に渡しません。completeも、観測したsequenceの整合性を示すもので、全データ到達の保証ではありません。

### 後処理で使うデータ

| 変数 | 形 | 内容 |
|---|---|---|
| `xyz` | N×3配列 | 各点のx、y、z。単位m、センサーのnative座標 |
| `intensity` | N要素 | 各点の反射強度 |
| `timestamps` | N要素 | 各点のLiDAR時刻。単位秒 |

ゼロ距離の除外やROI（対象範囲）の絞り込みは、後処理側で行ってください。
点は約0.1秒の間に順次測定されるため、移動中のSLAMなどでは各点の時刻を使うことがあります。

**このサンプルでは受信・復号・on_frameを同じスレッドで実行します。**
重い物体検出やSLAMを直接呼ぶと、その間に受信バッファが溜まります。
重い後処理は、容量制限付きキューを介して別スレッド／プロセスに渡す構成にしてください。
Open3Dビューアは「受信＋復号」と「描画」を分離し、表示待ちを最新1フレームに制限しています。

## 5. 実機がない場合に試す

### PCAPをファイルとして直接読む：ターミナルは1つ

```bash
python -m scripts.fetch_pcap
python -m e1r_decoder.decode_pcap --pcap testdata/e1r_frames.pcap --output output/pcap --format both
```

`fetch_pcap` は公開E1R PCAPを取得し、サイズとSHA-256を検査します。PCAP本体はリポジトリに含めていません。
この方法はUDP再送を使わず、ファイルから直接復号します。

### 実機の代わりにPCAPをUDP再送する：ターミナルを2つ開く

**「端末1」「端末2」は、別のPCではなく、同じPCで開いた2つのターミナルのウィンドウ／タブです。**
WindowsならPowerShell、Ubuntuならターミナルを2つ開きます。
受信プログラムが待機し続けるため、再送プログラムを別のウィンドウで動かします。

```text
同じPCの中
  再送用ターミナル：PCAP → UDP送信 → 127.0.0.1:6699
                                           ↓
  受信用ターミナル：点群の受信・表示 ← UDP受信
```

最初に `python -m scripts.fetch_pcap` でPCAPを取得してください。

**① 受信用ターミナル**：プロジェクトフォルダーに移動し、次を実行します。

```bash
python -m e1r_decoder.viewer --bind-ip 127.0.0.1 --msop-port 6699
```

**② 再送用ターミナル**：同じフォルダーに移動し、①の `READY` を確認してから次を実行します。

```bash
python -m e1r_decoder.replay --pcap testdata/e1r_frames.pcap --dst-ip 127.0.0.1 --dst-port 6699 --realtime
```

Ubuntuでは新しく開いたターミナルでも `source .venv/bin/activate` を実行してください。
Windowsでは両方とも `python` の代わりに `.\.venv\Scripts\python.exe` を使います。
`127.0.0.1` は自分自身のPCを指すアドレスです。実機の送信先IPには使用しません。

記録は約5秒分です。再送が終わると点群更新も止まり、ビューアは最後の表示を残します。
もう一度同じreplayコマンドを実行すると、再び再送できます。
サンプルコードを試す場合は、①を `python receive_points.py` に置き換えてください。
**実機が送信する場合、この再送用ターミナルは不要です。**

## 6. よく使う設定・困ったとき

| 設定 | 対象 | 意味 |
|---|---|---|
| `--msop-port 6699` / `--difop-port 7788` | live・viewer | センサーの送信先ポートに合わせる |
| `--source-ip IP` | live・viewer | 指定したセンサーからのみ受信 |
| `--duration 10` | live・viewer | 約10秒で終了 |
| `--debug 3` | live・decode_pcap | 先頭3個の有効MSOPの詳細を表示 |
| `--stats-json stats.json` | live・viewer・decode_pcap | 統計をJSON保存 |
| `--format npz` / `pcd` / `both` | live・decode_pcap | 保存形式。既定はnpz |
| `--point-size 3` / `--fps 30` | viewer | 点の表示サイズ／最大表示更新頻度 |
| `--realtime` | replay | 記録時の時間間隔で再送 |
| `--rate 2` / `--rate 0` | replay | 2倍速／待機なし。realtimeと同時指定不可 |

- **READYのままで点が来ない**：送信先IP、PCの有線LAN IP、サブネット、ポート、センサーの送信状態、ファイアウォールのUDP許可を確認してください。
- **ポート使用中というエラー**：同じポートを使うlive・viewer・サンプルが残っていないか確認してください。
- **Open3Dをimportできない**：使用中のPython環境に `python -m pip install -e '.[viewer]'` で追加してください。
- **ウィンドウが作れない**：OpenGLを利用できるデスクトップ環境が必要です。表示なしのliveで先に受信を確認できます。
- **最大速度replayで欠落する**：無欠落は保証していません。まず `--realtime` で確認してください。

## 7. データの扱いと未検証事項

- XYZはfloat32、timestampはfloat64。距離はraw値×0.005 m、方向はsigned int16÷32768。軸入れ替えや座標補正はしません。
- 各点の `timestamp = packet timestamp + time_offset`。TimeOffsetは公式rs_driverに合わせてマイクロ秒から秒へ変換します。
- PCAP捕捉時刻、ホスト受信時刻、LiDAR時刻は別物です。今回のPCAPのLiDAR時刻は約69,423秒から始まり、Unix時刻との同期・epochは未検証です。
- 点群配列には `time_offset, packet_sequence, point_index, attribute, distance_raw, dx_raw, dy_raw, dz_raw` もあります。未知フィールドを意味付けしません。
- ゼロ距離やintensity 0も復号時には残します。公式の既定0–200 m判定と異なり、範囲外でもXYZを復元します。
- 順序異常・重複は受信順に保持します。大きな順序異常やフレーム全体の欠落はsequenceだけでは正確に判定できません。
- ビューアの輝度調整と非有限XYZの除外は表示だけです。元データを変更しません。DIFOPは復号・集計しますが、ビューアではIMUを表示・保存しません。
- IMUは **IMPLEMENTED / SYNTHETICALLY TESTED / NOT VALIDATED WITH REAL DIFOP**。
- **physical unit is not yet verified**。IMU単位・軸・校正、firmware差異、実機受信、Ubuntu／Jetsonでの動作は未検証です。
- PCAP入力はEthernetのIPv4/IPv6 UDP。IP断片の再構成は非対応です。

## 8. テスト・公式比較（開発者向け）

2026-09-15、Windows x86_64 / Python 3.12でpytest 33件成功。
公開PCAPの14,184パケット・1,361,664点・50フレーム（partial 2）について、公式rs_driverとXYZ・intensity・timestamp・境界が一致しました。
XYZ・timestampの最大差は0でした。等速localhost再送は無欠落、Open3D実ウィンドウでの描画も確認済みです。
これは実機を接続した試験ではありません。詳細な生成レポートはGit管理対象外です。

```bash
python -m scripts.fetch_pcap
python -m pytest -q
```

公式比較は、公式C++実装をビルドした場合に実行します。実行ファイルがなければそのテストはskipし、公式比較PASSとは扱いません。
Open3Dが未インストールならOpen3D実geometryテストもskipします。

Ubuntuでのビルド手順:

```bash
git clone https://github.com/RoboSense-LiDAR/rs_driver.git vendor/rs_driver
git -C vendor/rs_driver checkout 897b14d3bdb6186a75df27ba51b65b5bd5557723
mkdir -p build
c++ -std=c++14 -O2 -Ivendor/rs_driver/src scripts/rs_reference.cpp -o build/rs_reference
python -m scripts.validate_reference --executable build/rs_reference
```

Windowsで使用したビルド手順（Zigは比較検証専用）:

```powershell
.\.venv\Scripts\python.exe -m pip install ziglang==0.16.0
git clone https://github.com/RoboSense-LiDAR/rs_driver.git vendor/rs_driver
git -C vendor/rs_driver checkout 897b14d3bdb6186a75df27ba51b65b5bd5557723
New-Item -ItemType Directory -Force build
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path (Get-Location) 'build/zig-cache'
.\.venv\Scripts\python.exe -m ziglang c++ -std=c++14 -D_USE_MATH_DEFINES -O2 -Ivendor/rs_driver/src scripts/rs_reference.cpp -lws2_32 -o build/rs_reference.exe
.\.venv\Scripts\python.exe -m scripts.validate_reference
```

`python -m scripts.inspect_pcap` でPCAPの統計を生成します。
`python -m scripts.smoke_viewer` で約8秒の実ウィンドウ＋localhost再送試験を行い、画像と統計を `output/` に保存します。

## 出典・ライセンス

- [RoboSense rs_driver](https://github.com/RoboSense-LiDAR/rs_driver/tree/897b14d3bdb6186a75df27ba51b65b5bd5557723)：パケット仕様の参照元およびフレーム分割処理の移植元。関連する著作権通知・BSD-3-Clause条件・免責事項は [licenses/rs_driver.txt](licenses/rs_driver.txt) に保持しています。公式ドライバ本体は同梱していません。
- 実測PCAPはリポジトリに同梱していません。必要な場合のみ [EdgeFirstAI lidarpub](https://github.com/EdgeFirstAI/lidarpub/tree/c7d4da23d6c9b33a06dda70e623b28cfbf767f65) から取得します。外部データの利用条件は取得元で確認してください。
