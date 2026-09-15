# RoboSense E1R UDP decoder

Repository: [yuki1125/robosense-e1r-decoder](https://github.com/yuki1125/robosense-e1r-decoder) (Private)

E1Rのnative座標で点群とraw IMUを取り出すPythonパッケージです。
PCAP / live UDP → 共通デコーダ → 共通フレーム組立 → NPZ / PCD。
復号CLIはGUI、ROS、GPU不要です。Python 3.10+、NumPy、dpktを使用します。
オプションでOpen3Dによるリアルタイム表示も利用できます。

## インストールと実行（Ubuntu 22.04）

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m scripts.fetch_pcap
python -m e1r_decoder.decode_pcap --pcap testdata/e1r_frames.pcap --debug 3
python -m e1r_decoder.decode_pcap --pcap testdata/e1r_frames.pcap --output output/ --format both
python -m pytest -q
```

Windowsでは作成済みの `.venv\Scripts\python.exe` を `python` の代わりに使用できます。
GitHubから取得した場合、仮想環境は各自作成してください。PCAP本体はリポジトリに含めず、上記 `scripts.fetch_pcap` で検証済みの公開データを取得します。
検証実行環境はWindows x86_64 / Python 3.12です。Ubuntu・Jetsonでの実機試験は未実施です。

## Live / replay

端末1（受信準備ができると `READY` を表示）:

```bash
python -m e1r_decoder.live --bind-ip 0.0.0.0 --msop-port 6699 --difop-port 7788 --output output/live
```

端末2:

```bash
python -m e1r_decoder.replay --pcap testdata/e1r_frames.pcap --dst-ip 127.0.0.1 --dst-port 6699 --realtime
python -m e1r_decoder.replay --pcap testdata/e1r_frames.pcap --dst-ip 127.0.0.1 --dst-port 6699 --rate 0
```

`--rate 2` は2倍速、既定値1は等速、0は待機なしです。
`--realtime` と `--rate` は同時指定できません。送信するのはUDP payloadのみです。
捕捉時刻が逆行した箇所は待機せず、ファイル順を保持します。
`--source-port 7788 --dst-port 7788` でDIFOPを含む別PCAPの再送も可能です。

実機ではネットワーク設定を機器側で行い、同じliveコマンドに切り替えます。
`--source-ip SENSOR_IP` で受信元を限定できます。1プロセスにつき1センサーを使用してください。
`--duration 10` または `--max-packets N` で自動停止できます。Ctrl+Cでも残余フレームをpartialとして保存します。
`--stats-json path.json` は集計保存、`--debug N` は先頭N個の有効MSOP表示です。
出力ディレクトリは実行ごとに分けてください（同じframe番号のファイルは上書き、IMU JSONLは追記）。

## Open3Dリアルタイム表示

Open3Dは描画用の追加依存です（通常の復号には不要）。

```bash
python -m pip install -e '.[viewer]'
python -m e1r_decoder.viewer --bind-ip 0.0.0.0 --msop-port 6699
```

Windowsの作成済み環境にはOpen3D 0.19.0をインストール済みです。

```powershell
.\.venv\Scripts\python.exe -m e1r_decoder.viewer --bind-ip 0.0.0.0 --msop-port 6699
```

実機なしでは、ビューアが `READY` を表示した後、別端末で次を実行します。
同じポートを使う `live` CLIとビューアは同時起動しないでください。

```powershell
.\.venv\Scripts\python.exe -m e1r_decoder.replay --pcap testdata/e1r_frames.pcap --dst-ip 127.0.0.1 --dst-port 6699 --realtime
```

- マウスで視点操作できます。ウィンドウを閉じるかCtrl+Cで受信も終了します。
- `--point-size 3`、`--fps 30`、`--width 1280 --height 720` で表示を調整できます。
- `--duration 10` で自動終了、`--stats-json output/viewer.json` で受信・描画統計を保存できます。
- 起動時に視野を合わせ、最初のcomplete frameでも一度だけ再調整します。その後は視点を保持します。
- XYZはnative座標のままです。intensityをグレースケール表示し、見やすさのため輝度を `0.25 + 0.75 * sqrt(intensity / 255)` とします。元データは変更しません。
- ゼロ距離・ゼロintensityの点も保持します。描画に渡す際のみ非有限XYZを除外します。
- 受信・復号を別スレッドで処理し、描画はメインスレッドで行います。表示待ちは最新フレーム1個までです。
- `display_skipped_frames` は描画待ちの置換数で、UDPパケット欠落数ではありません。partial frameも表示します。点群を蓄積する方式ではありません。
- DIFOPも共通受信処理で復号・集計しますが、このビューアはIMUを表示・保存しません。点群保存は既存CLIを使用してください。

デスクトップとOpenGLコンテキストが必要です。ウィンドウを作成できない場合は理由を表示して終了します。
Jetson上のOpen3D導入・描画は未検証です。
実ウィンドウ＋localhost再送の再現試験は `python -m scripts.smoke_viewer` で行えます（約8秒で閉じ、`output/viewer_smoke.png` に画像を保存）。
使用APIの根拠: [Open3D non-blocking visualization](https://open3d.org/docs/release/tutorial/visualization/non_blocking_visualization.html)。

## API / 出力

```python
from e1r_decoder import decode_msop, decode_difop, FrameAssembler

assembler = FrameAssembler()
packet = decode_msop(payload, capture_timestamp=None)
frame = assembler.push(packet)  # 境界で前フレームを返す。その他はNone
last_partial = assembler.flush()
```

- `E1RPacket.points` / `E1RFrame.points` はNumPy構造化配列。XYZはfloat32、時刻はfloat64です。
- `x, y, z, intensity, timestamp, time_offset, packet_sequence, point_index, attribute`、生の距離・方向を保持します。
- `E1RPoint` dataclassも提供します。通常の処理経路では各点のPythonオブジェクトを作りません。
- NPZは上記全フィールドを名前付き配列で保存します。PCDはbinary形式のXYZ/intensityです。
- frame JSONにはpacket数、point数、時刻範囲、sequence列、complete、不完全理由を保存します。
- IMUは `imu.jsonl` に保存します。NaN/InfはJSON内では文字列で表し、復号器内のfloatは保持します。
- packetの `raw_payload` にMSOPの未知・reserved領域を残します。意味付けはしません。
- 不正payloadはAPIでは `PacketError`、CLIでは理由別に集計して処理を継続します。

## 時刻・座標・フレーム品質

公式ソースの固定版を根拠に、distance×0.005 m、signed direction÷32768でXYZを計算します。
軸変換・ROI・intensity除外・距離除外はありません。distance=0の点も保持します。
公式既定の0–200 m判定との違いは [VALIDATION.md](VALIDATION.md) に記載しています。

LiDAR時刻は6-byte秒＋4-byteマイクロ秒、point time offsetもマイクロ秒です。
`timestamp = packet_timestamp + time_offset` とします。
PCAP時刻は `capture_timestamp`、liveのホスト受信時刻は `receive_timestamp` に分離します。
ホスト時刻でLiDAR時刻を置換しません。このPCAPのLiDAR時計は約69,423秒からであり、
PCAPのUnix時刻とは一致しません。同期状態・epochは検証していません。

境界は公式 `SplitStrategyBySeq` の許容幅10を含めて再現します。
288パケット固定では分割しません。重複・順序異常を削除／整列せず、受信順に保持します。
初回、EOF、連続性異常、開始sequence不一致、既観測最大sequenceに届かないフレームはpartialです。
`complete` は観測できたsequenceの整合性を示し、送信された全データの到達保証ではありません。
一度も観測できなかった末尾、フレーム全体の欠落、大きな順序逆転と真の巻き戻りの区別は、
このsequence方式だけでは証明できません。`sequence_gaps` は前進跳躍の合計で、UDP総欠落数とは異なります。

## 公式比較の再現

公式実装は比較時のみ必要です。通常動作にはC++は不要です。

```bash
git clone https://github.com/RoboSense-LiDAR/rs_driver.git vendor/rs_driver
git -C vendor/rs_driver checkout 897b14d3bdb6186a75df27ba51b65b5bd5557723
mkdir -p build
c++ -std=c++14 -O2 -Ivendor/rs_driver/src scripts/rs_reference.cpp -o build/rs_reference
python -m scripts.validate_reference --executable build/rs_reference
python -m scripts.inspect_pcap
```

Windowsで実行したビルド（Zigは検証専用依存）:

```powershell
.\.venv\Scripts\python.exe -m pip install ziglang==0.16.0
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path (Get-Location) 'build/zig-cache'
.\.venv\Scripts\python.exe -m ziglang c++ -std=c++14 -D_USE_MATH_DEFINES -O2 -Ivendor/rs_driver/src scripts/rs_reference.cpp -lws2_32 -o build/rs_reference.exe
.\.venv\Scripts\python.exe -m scripts.validate_reference
```

pytestは実PCAPがなければ失敗します。公式比較実行ファイルだけがなければ該当試験を明示的にskipします。
skipを公式比較PASSとは扱いません。UDP試験の等速再送では全点一致を要求し、最大速度では欠落数を記録します。

## 未検証・制限

- IMU: **IMPLEMENTED / SYNTHETICALLY TESTED / NOT VALIDATED WITH REAL DIFOP**。
- **physical unit is not yet verified**。IMU axis convention / calibrationはUNKNOWNです。
- firmware差異、実機接続、実DIFOP、IMU同期精度、Ubuntu/aarch64性能はNOT VALIDATEDです。
- PCAP入力はEthernet（VLANを含む）のIPv4/IPv6 UDP。IP断片再構成は非対応です。
- 最大速度replayの無欠落は保証しません。実時間相当の検証結果と区別してください。
- 公式の境界方式は大きな順序異常を巻き戻りと判断し得ます。壊れたsequence列では正しいフレームを保証できません。
- 座標の幾何的な正確さ・測距精度の実機校正試験は未実施です。

## 出典・ライセンス

- [RoboSense rs_driver](https://github.com/RoboSense-LiDAR/rs_driver/tree/897b14d3bdb6186a75df27ba51b65b5bd5557723): 仕様と分割処理の根拠。BSD-3-Clauseの通知を `licenses/rs_driver.txt` に保存。
- [EdgeFirstAI lidarpub](https://github.com/EdgeFirstAI/lidarpub/tree/c7d4da23d6c9b33a06dda70e623b28cfbf767f65): 実測PCAP。リポジトリのライセンスを `licenses/lidarpub.txt` に保存。
