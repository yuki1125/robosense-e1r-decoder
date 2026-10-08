# RoboSense E1R Pythonデコーダ

RoboSense E1Rが送信するUDPパケットを受信し、各点の3次元座標（x・y・z）、反射強度、測定時刻を取り出すPythonライブラリ。
点群の保存、Open3Dによるリアルタイム表示、物体検出やSLAMへのデータ入力に使える。物体検出・SLAM自体や、センサーの設定変更機能は含まない。

```text
E1R → Ethernet → UDP受信 → パケットの復号 → フレームにまとめる → 保存・表示・後処理
```

実機なしでも、公開PCAP（通信を記録したファイル）で試せる。PCAP本体はリポジトリに含めていない。
**実機での動作は未検証。** 公開PCAPの復号、同じPC内でのUDP送受信、Open3D表示、合成IMUデータでの試験を実施済み。

## 1. インストール

必要なもの：

- Python 3.10以上とGit
- 実機を使う場合：E1R、メーカー指定の給電機器、Ethernetケーブル、有線LANを備えたPC
- 3D表示を使う場合：OpenGLを利用できるデスクトップ環境

基本機能の依存ライブラリはNumPyとdpkt。復号にROSやGPUは不要。

```bash
git clone https://github.com/yuki1125/robosense-e1r-decoder.git
cd robosense-e1r-decoder
```

以降のコマンドは、このフォルダーで実行する。

### Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

新しいターミナルを開いたときも、`source .venv/bin/activate` で仮想環境を有効にする。

### Jetson / Linux ARM64

ARM64（aarch64）でも受信・復号・保存・`E1RSensor.read()` は同じコードを使う。CUDAは不要。
Jetson OrinではJetPack 6系（Ubuntu 22.04）のPython 3.10を想定する。32bit ARMとPython 3.9以前は対象外。

コードを取得したフォルダーで実行する。

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m e1r_decoder.live --bind-ip 0.0.0.0 --msop-port 6699
```

3D表示も使う場合は、受信を止めてから次を実行する。

```bash
sudo apt-get install -y libgl1 libgomp1
python -m pip install -e '.[viewer]'
python -m e1r_decoder.viewer --fps 10
```

Linux ARM64のviewerは **Python 3.10 / 3.11** が対象。ARM64向け公式wheelがあるOpen3D 0.18.0とNumPy 1.xを自動選択する。その他の環境では従来のOpen3D 0.19を使う。
Python 3.12以降のLinux ARM64では基本機能のみ利用でき、viewer用の依存関係はインストールできない。表示する場合はPython 3.10 / 3.11の環境を用意する。
Open3DにはデスクトップとOpenGLが必要。SSHのみの環境では `live` または `E1RSensor` で取得・保存する。

依存パッケージの根拠：[Open3D公式wheel一覧](https://pypi.org/project/open3d/0.18.0/#files)、[Open3D ARM対応](https://www.open3d.org/docs/0.19.0/arm.html)、[JetPack 6の構成](https://developer.nvidia.com/embedded/jetpack-sdk-60)。Jetson実機での受信・描画・処理速度は未検証。

### Windows（PowerShell）

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Windowsでは、以降の例の `python` を `.\.venv\Scripts\python.exe` に置き換える。
Open3Dとテスト用ライブラリは、必要に応じて後の手順で追加する。

## 2. センサー接続とネットワーク設定

1. E1Rにメーカー指定の方法で給電し、EthernetでPCに接続する。
2. センサーのIPアドレスとサブネットマスクを確認する。
3. PCの有線LANに、センサーと通信できるIPアドレスを設定する。
4. センサーのUDP送信先に、PCの有線LANのIPアドレスと受信ポートを設定する。
5. PCのファイアウォールでUDP受信を許可する。

センサーの設定方法と給電条件は機器の公式資料を参照。このコードでは、センサーやPCのネットワーク設定は変更しない。

同一サブネットで接続する場合の設定例：

| 項目 | 設定例 |
|---|---|
| センサーのIP | `192.168.1.200` |
| PCの有線LANのIP | `192.168.1.100` |
| 両方のサブネットマスク | `255.255.255.0` |
| センサーのUDP送信先IP | `192.168.1.100` |
| 点群用の送信先ポート（MSOP） | `6699` |
| 機器情報・IMU用の送信先ポート（DIFOP） | `7788` |

これは工場出荷時の設定ではなく一例。実際の機器設定に合わせる。PCとセンサーには、それぞれ異なるIPを割り当てる。

## 3. 実機からの受信・保存・表示

センサーの送信設定を済ませたら、用途に応じて次のいずれかを実行する。
**live、viewer、4章のサンプルは同じUDPポートを使うため、同時に起動せず、切り替える前に終了する。**

### 受信を確認する

```bash
python -m e1r_decoder.live --bind-ip 0.0.0.0 --msop-port 6699 --difop-port 7788 --debug 3
```

- `READY`：受信待機を開始した状態。データが届いているかは、その後の表示で確認する。
- パケット情報：最初の3個の有効な点群パケットについて詳細を表示する。
- `Frame ... packets=... points=...`：点群が1フレーム分まとまると表示する。
- Ctrl+C：受信を終了し、受信数や不正パケット数などの統計を表示する。

`--bind-ip` にはPC側のIPを指定する。`0.0.0.0` はPCのすべてのIPv4インターフェースで待ち受ける指定。
センサー側の送信先には、PCの実際の有線LANのIPを設定する。
`--source-ip 192.168.1.200` を追加すると、受信元を限定できる。1プロセスにつき1台のセンサーを想定している。

### 点群を保存する

```bash
python -m e1r_decoder.live --output output/live --format both
```

`output/live/` にフレーム単位で保存する。

| ファイル | 内容 |
|---|---|
| `frame_000001.npz` | NumPyで読み込めるXYZ、反射強度、各点の時刻など |
| `frame_000001.pcd` | XYZ、反射強度を含むbinary PCD |
| `frame_000001.json` | 時刻範囲、パケット数、不完全なフレームの理由など |
| `imu.jsonl` | DIFOPから取り出したIMUの生の値（受信した場合） |

同じ番号の点群ファイルは上書きされ、IMUファイルには追記されるため、出力先は実行ごとに分ける。
`--duration 10` を追加すると約10秒で終了する。

### Open3Dでリアルタイム表示する

初回のみOpen3Dをインストールする。

```bash
python -m pip install -e '.[viewer]'
```

```bash
python -m e1r_decoder.viewer --bind-ip 0.0.0.0 --msop-port 6699
```

受信した点群をウィンドウに表示する。マウスで視点を操作でき、ウィンドウを閉じるかCtrl+Cで終了する。
`--point-size 3` で点の表示サイズを変更できる。表示するのは最新フレームのみで、過去の点群の蓄積や保存は行わない。

## 4. Pythonで点群を取得する

`E1RSensor` を使うと、通常のループから `frame, imu = sensor.read()` でデータを取得できる。
UDP受信と復号は内部のスレッドで動き続けるため、後処理をコールバックに書く必要はない。

次のコードを `receive_points.py` として保存する。1〜2章のインストールと接続設定が前提。
liveやviewerは同時に起動しない。実機がない場合は、5章のPCAP再送で試せる。

```python
import numpy as np
from e1r_decoder import E1RSensor


def main():
    with E1RSensor(bind_ip="0.0.0.0", msop_port=6699, difop_port=7788) as sensor:
        print("受信待機中。終了するにはCtrl+C", flush=True)
        while True:
            try:
                frame, imu = sensor.read(timeout=2.0)
            except TimeoutError:
                print("フレーム待機中：接続とセンサーの送信設定を確認")
                continue

            points = frame.points
            xyz = np.column_stack([points["x"], points["y"], points["z"]])
            intensity = points["intensity"]
            timestamps = points["timestamp"]
            print(f"Frame {frame.frame_index}: {len(points)}点")

            if imu is not None:
                print(f"加速度の生の値: {imu.accel_x_raw}, {imu.accel_y_raw}, {imu.accel_z_raw}")

            # ここに後処理を書く
            # detect_objects(xyz)
            # slam.update(xyz, timestamps)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
```

```bash
python receive_points.py
```

- `read()` は新しいフレームを待ち、フレームとIMUを返す。`timeout` 秒以内に取得できなければ `TimeoutError`。省略時は取得まで待つ。
- `frame.points` はXYZ・反射強度・時刻などを持つNumPy構造化配列。フレーム情報も使えるよう、配列だけでなく `frame` を返す。
- `imu` はフレームがまとまった時点で最後に受信したIMU。未受信なら `None`。点群と時刻同期した値ではなく、更新が止まれば古い値が返る。必要に応じて `timestamp` と `receive_timestamp` を確認する。
- 既定では完全なフレームのみ取得する。不完全なフレームも必要なら `complete_only=False` を指定する。
- 待機キューは既定で1フレーム。後処理が遅いと古いフレームを捨てて最新を残す。破棄数は `sensor.dropped_frames`、キュー容量は `queue_size` で指定できる。
- `with` を抜けると受信スレッドを停止し、UDPポートを解放する。

### フレームとは

複数のUDPパケットを、1回分のスキャンとしてまとめた点群。
公開PCAPでは約0.1秒に1フレーム（約10 Hz）、通常288パケット・27,648点が記録されている。
パケットのシーケンス番号から次のスキャンへの切り替わりを検出し、直前のフレームを取り出せる状態にする。固定のパケット数で分割する方式ではない。

受信開始直後や終了時、パケット欠落時などは不完全なフレーム（`frame.complete == False`）になる。
上のサンプルでは、これをスキップする。`complete` は観測したシーケンス番号の整合性に基づく判定であり、全データの到達を保証するものではない。

### 後処理に渡すデータ

| 変数 | 形 | 内容 |
|---|---|---|
| `xyz` | N×3配列 | 各点のx、y、z。単位m、センサー固有の座標系 |
| `intensity` | N要素 | 各点の反射強度 |
| `timestamps` | N要素 | 各点のLiDAR時刻。単位秒 |

Nはフレーム内の点数。例えば `xyz[0]` は先頭の点のx・y・zを表す。
座標は世界座標へ変換していない。LiDAR時刻もPCの現在時刻と一致するとは限らない。
ゼロ距離の除外や対象範囲の絞り込みは、後処理側で行う。
スキャン中にもセンサーが移動する場合は、各点の時刻を使って動きによる点群の歪みを補正できる。

受信・復号は内部スレッド、後処理は呼び出し側のスレッドで実行する。
全フレームの保存や全IMUサンプルの取得が必要な用途では、この最新データ取得APIではなく、`Pipeline` の `on_frame` / `on_imu` を使う。
CPU負荷の高いPython処理は受信スレッドにも影響するため、必要に応じて後処理を別プロセスへ分ける。UDP自体も無欠落を保証しない。

## 5. 実機なしで試す

公開PCAPを使い、ファイルからの復号とUDP受信を試せる。このPCAPにDIFOPは含まれないため、確認できるのは点群の処理のみ。

### 保存済みのPCAP / PCAPNGをOpen3Dで表示する

保存したE1Rのキャプチャファイルを直接開き、フレームごとに再生表示できる。センサー接続やUDP再送は不要。
Open3Dの導入後、ターミナル1つで実行する。

```bash
python -m pip install -e '.[viewer]'
python -m e1r_decoder.viewer --pcap "recordings/scan.pcap"
```

PCAPNGも同じコマンドで読み込める。形式は拡張子ではなくファイルの内容から判別する。

```bash
python -m e1r_decoder.viewer --pcap "recordings/scan.pcapng"
```

記録された受信時刻の間隔で等速再生し、終了後は最後の点群を表示したままにする。マウスで視点を操作し、ウィンドウを閉じるかCtrl+Cで終了する。

```bash
# 0.5倍速で繰り返し再生
python -m e1r_decoder.viewer --pcap "recordings/scan.pcapng" --rate 0.5 --loop

# 再生終了と同時にウィンドウを閉じる
python -m e1r_decoder.viewer --pcap "recordings/scan.pcap" --exit-on-end
```

- `--rate 2` は2倍速、`--rate 0` は待ち時間なし。描画が追いつかないフレームは省略し、最新の点群を表示する。
- `--msop-port` と `--difop-port` はファイル内の送信先ポートに合わせる。複数センサーの記録では `--source-ip` で1台を指定する。
- 先頭・末尾などの不完全なフレームも表示する。繰り返し再生では毎回フレームの組み立てをリセットする。
- 表示するのは点群。DIFOPがあれば復号・集計するが、IMUは描画しない。
- 対象はE1RのEthernet UDPキャプチャ。別機種の点群データや、任意のPCAPを表示する機能ではない。

### PCAPから直接復号する

```bash
python -m scripts.fetch_pcap
python -m e1r_decoder.decode_pcap --pcap testdata/e1r_frames.pcap --output output/pcap --format both
```

`fetch_pcap` はPCAPをダウンロードし、サイズとSHA-256を検査する。
`decode_pcap` はファイルから直接読み込むため、UDP再送は不要。

### PCAPをUDPで再送する

PCAPのデータをセンサーの代わりに送信し、受信プログラムを試す。
**同じPCでターミナルを2つ開き、一方で受信、もう一方で再送を実行する。**
ターミナルとはコマンドを入力するウィンドウのことで、WindowsではPowerShellなどが使える。

```text
再送プログラム：PCAP → UDP送信 → 127.0.0.1:6699 → 受信プログラム
```

先に `python -m scripts.fetch_pcap` でPCAPを取得し、表示する場合は `python -m pip install -e '.[viewer]'` でOpen3Dもインストールする。
両方のターミナルでプロジェクトフォルダーに移動し、1章で作ったPython環境を使う。

**受信用ターミナル：**

```bash
python -m e1r_decoder.viewer --bind-ip 127.0.0.1 --msop-port 6699
```

**再送用ターミナル：** 受信側の `READY` を確認してから実行する。

```bash
python -m e1r_decoder.replay --pcap testdata/e1r_frames.pcap --dst-ip 127.0.0.1 --dst-port 6699 --realtime
```

`127.0.0.1` は自分自身のPCを指す。実機の送信先IPには使わない。
記録は約5秒分で、再送が終わるとビューアの更新も止まる。再度replayを実行すると、同じデータを再送できる。
4章のサンプルを試す場合は、受信用のコマンドを `python receive_points.py` に置き換える。
実機がデータを送信する場合、再送プログラムは不要。

## 6. オプションとトラブルシューティング

| オプション | 対象 | 内容 |
|---|---|---|
| `--pcap PATH` | viewer | PCAP / PCAPNGを直接再生。省略時は実UDP受信 |
| `--rate 0.5` / `--loop` / `--exit-on-end` | viewer（ファイル入力） | 再生速度／繰り返し／再生終了時に閉じる |
| `--msop-port 6699` / `--difop-port 7788` | live・viewer | センサーまたは記録内の送信先ポートに合わせる |
| `--source-ip IP` | live・viewer | 指定したセンサーからのみ受信 |
| `--duration 10` | live・viewer | 約10秒で終了 |
| `--debug 3` | live・decode_pcap | 最初の3個の有効MSOPパケットの詳細を表示 |
| `--stats-json stats.json` | live・viewer・decode_pcap | 統計をJSONで保存 |
| `--format npz` / `pcd` / `both` | live・decode_pcap | 保存形式。既定値はnpz |
| `--point-size 3` / `--fps 30` | viewer | 点の表示サイズ／最大表示更新頻度 |
| `--realtime` | replay | 記録時の時間間隔で再送 |
| `--rate 2` / `--rate 0` | replay | 2倍速／待機なし。realtimeと同時指定不可 |

- **READYのままで点群が届かない**：センサーの送信状態、送信先IP、PCの有線LANのIP、サブネット、ポート、ファイアウォールを確認する。
- **ポートが使用中**：同じポートを使うlive・viewer・サンプルが起動していないか確認する。
- **Open3Dをimportできない**：使用中のPython環境で `python -m pip install -e '.[viewer]'` を実行する。
- **ウィンドウを開けない**：OpenGLを利用できるデスクトップ環境が必要。表示を使わないliveで受信を確認する。
- **最大速度の再送で欠落する**：送信速度が受信処理の速度を超えると欠落することがある。まず `--realtime` で試す。

## 7. データ仕様と制限

- XYZはfloat32、timestampはfloat64。距離はraw値×0.005 m、方向は符号付きint16÷32768。軸の入れ替えや座標補正は行わない。
- 各点の `timestamp = packet timestamp + time_offset`。TimeOffsetは公式rs_driverに合わせてマイクロ秒から秒へ変換する。
- PCAPの記録時刻、PCの受信時刻、センサーの測定時刻は区別して扱う。センサー時刻の起点とUnix時刻への同期は未検証。
- 点群配列には `time_offset, packet_sequence, point_index, attribute, distance_raw, dx_raw, dy_raw, dz_raw` も保持する。未知フィールドの意味は推定しない。
- ゼロ距離や反射強度0の点も残す。公式実装の既定の距離判定（0–200 m）による除外は行わず、範囲外でもXYZを復元する。
- 順序異常や重複があっても受信順に保持する。大きな順序異常やフレーム全体の欠落は、シーケンス番号だけでは正確に判定できない。
- ビューアの輝度調整とNaN・Infを含むXYZの除外は表示にのみ適用し、元データは変更しない。DIFOPは復号・集計するが、ビューアではIMUを表示・保存しない。
- IMUは **IMPLEMENTED / SYNTHETICALLY TESTED / NOT VALIDATED WITH REAL DIFOP**。値は単位変換せず保持する。**physical unit is not yet verified**。
- 実測DIFOP、IMUの単位・軸・校正、ファームウェアによる差異、実機での受信は未検証。Ubuntu／Jetsonでの実行も未検証。
- PCAP入力はEthernetのIPv4/IPv6 UDPに対応。IPフラグメントの再構成には非対応。

## 8. テストと公式実装との比較

公開PCAPの14,184パケット・1,361,664点・50フレーム（不完全なフレーム2個）で、公式rs_driverとXYZ・反射強度・各点の時刻・フレーム境界が一致することを確認済み。
IMUは合成パケットで試験している。

```bash
python -m pip install -e '.[test]'
python -m scripts.fetch_pcap
python -m pytest -q
```

公式比較には、公式C++実装を使った比較用プログラムのビルドが必要。
実行ファイルがない場合は比較テストをスキップする。Open3Dがない場合も、対応するテストをスキップする。

C++コンパイラーを使うビルド例（Ubuntu）：

```bash
git clone https://github.com/RoboSense-LiDAR/rs_driver.git vendor/rs_driver
git -C vendor/rs_driver checkout 897b14d3bdb6186a75df27ba51b65b5bd5557723
mkdir -p build
c++ -std=c++14 -O2 -Ivendor/rs_driver/src scripts/rs_reference.cpp -o build/rs_reference
python -m scripts.validate_reference --executable build/rs_reference
```

`python -m scripts.inspect_pcap` でPCAPの統計を確認できる。
`python -m scripts.smoke_viewer` は、UDP再送とOpen3D表示を組み合わせた試験を実行し、画像と統計を `output/` に保存する。

### UDP viewer validation

The live Open3D viewer receives and decodes UDP in a spawned process. Open3D
render calls can hold Python's GIL; a receiver thread in the rendering process
cannot drain its UDP socket during such a call. The input process uses a
one-slot latest-frame mailbox and a bounded pipe, and the display keeps its own
one-slot mailbox. Slow rendering may skip display frames without blocking
packet reception. All Open3D operations remain on the main thread. Programs
calling `viewer.run()` must use an `if __name__ == "__main__":` guard.

The checks have separate guarantees:

- Offline decoding and the pinned C++ reference comparison verify packet,
  point, timestamp, and frame correctness without UDP timing.
- The 1x UDP tests and real Open3D smoke require all 14,184 packets,
  1,361,664 points, 50 frames, and 2 partial frames. The capture already has
  `sequence_gaps == 2`; this is the baseline, not a zero-gap recording.
- The smoke sender runs in its own process at the recorded rate (`rate=1`).
  It starts after both receive sockets are bound. The receiver finishes at the
  exact packet count; 30 seconds is a failure watchdog, not the replay length.
  Missing packets, additional gaps, invalid packets, or observed kernel drops
  still fail the smoke. A 300 ms GIL-holding render-stall regression also runs
  with a small per-socket buffer, without changing OS settings.
- The existing `rate=0` UDP case is maximum-speed stress. It records loss and
  checks exact point data when no loss occurs; it does not promise lossless
  reception at unlimited rates.

`output/viewer_smoke_sender.json` records count, rate, and actual sender time.
`output/viewer_smoke.json` includes actual `msop_rcvbuf_bytes` /
`difop_rcvbuf_bytes` (the OS may cap requests), decoder counts,
`rendered_frames`, and `display_skipped_frames`. The latter includes
`input_skipped_frames` from the input mailbox. Linux additionally reports
`udp_socket_drops` from the sockets' `/proc/net/udp` entries before closing;
this field is omitted if those counters are unavailable, never inferred from
sequence gaps. CI retains the smoke output and UDP stress evidence even on
failure.

Hosted ARM64 CI and localhost replay do not validate a physical Jetson Orin,
sensor Ethernet delivery, real DIFOP/IMU data, or unlimited-rate performance.
