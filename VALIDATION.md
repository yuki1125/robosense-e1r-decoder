# E1R validation record

実行日: 2026-09-15。実機なしで実施した検証です。

## 結果

| 項目 | 結果 |
|---|---|
| MSOP decoding | PASS |
| XYZ validation against rs_driver | PASS |
| Frame reconstruction | PASS（実測PCAP・合成異常列） |
| PCAP offline decoding | PASS |
| UDP replay | PASS（等速無欠落、最大速度は欠落あり） |
| Live UDP receiver | PASS（localhost、MSOPと合成DIFOP） |
| DIFOP decoder | IMPLEMENTED |
| IMU synthetic test | PASS |
| IMU real E1R validation | BLOCKED（実DIFOP未入手） |

`python -m pytest -q`: **33 passed in 28.83s**（Open3D追加後）。この実行ではskipはありません。
表示輝度調整後の `python -m pytest tests/test_viewer.py -q` も **4 passed**。
Windows x86_64、Python 3.12、NumPy 2.5.3、dpkt 1.9.8、pytest 9.1.1。
公式C++比較はZig 0.16.0のC++コンパイラで実行しました。

## データの同一性

- 出典: [EdgeFirstAI/lidarpub](https://github.com/EdgeFirstAI/lidarpub/tree/c7d4da23d6c9b33a06dda70e623b28cfbf767f65)
- commit: `c7d4da23d6c9b33a06dda70e623b28cfbf767f65`
- パス: `testdata/e1r_frames.pcap`
- LFS pointerのsize: **17,843,496 bytes**
- LFS OID / 実ファイルSHA-256: `e5e3529e4ddf883376448d4e20fe1dd21a979ed8b37a96b8c7a8d7d3f43028eb`

Git LFSで本体を取得し、Git内のpointerとサイズ・SHA-256が一致することを確認しました。
`scripts.fetch_pcap` と実PCAP integration testでも同じ同一性検査を行います。

## 仕様の一次情報

公式commit: **897b14d3bdb6186a75df27ba51b65b5bd5557723**。

- [decoder_RSE1.hpp](https://github.com/RoboSense-LiDAR/rs_driver/blob/897b14d3bdb6186a75df27ba51b65b5bd5557723/src/rs_driver/driver/decoder/decoder_RSE1.hpp): wire構造、XYZ、IMU、timestamp計算。
- [basic_attr.hpp](https://github.com/RoboSense-LiDAR/rs_driver/blob/897b14d3bdb6186a75df27ba51b65b5bd5557723/src/rs_driver/driver/decoder/basic_attr.hpp): UTC時刻パース。
- [split_strategy.hpp](https://github.com/RoboSense-LiDAR/rs_driver/blob/897b14d3bdb6186a75df27ba51b65b5bd5557723/src/rs_driver/driver/decoder/split_strategy.hpp): sequence許容幅10、巻き戻り、uint16の挙動。
- [section.hpp](https://github.com/RoboSense-LiDAR/rs_driver/blob/897b14d3bdb6186a75df27ba51b65b5bd5557723/src/rs_driver/driver/decoder/section.hpp): 距離範囲判定。

offsetはUDP payload先頭からの0-based値。block内offsetはblock先頭からです。

| フィールド | offset / size | 解釈 |
|---|---|---|
| MSOP magic | 0 / 4 | 55 AA 5A A5 |
| sequence | 4 / 2 | big endian uint16 |
| protocol version | 6 / 2 | big endian uint16、意味の追加解釈なし |
| return mode / time mode | 8 / 1、9 / 1 | raw byte |
| MSOP timestamp | 10 / 10 | big endian 6-byte seconds + 4-byte microseconds |
| blocks | 32 / 1152 | 96 × 12 bytes |
| block time offset | +0 / 2 | big endian uint16、×1e-6秒 |
| block distance | +2 / 2 | big endian uint16、×0.005 m |
| block direction XYZ | +4,+6,+8 / 各2 | big endian int16、÷32768 |
| intensity / attribute | +10 / 1、+11 / 1 | uint8、attributeの意味はUNKNOWN |
| MSOP tail | 1184 / 16 | reserved、解釈しない |
| DIFOP magic | 0 / 8 | A5 FF 00 5A 11 11 55 55 |
| DIFOP timestamp | 103 / 10 | MSOPと同じ時刻形式 |
| IMU | 208 / 24 | big endian float32、ax ay az gx gy gz |

MSOPは1200 bytes、DIFOPは256 bytes。公式ソースのpacked structと一致します。
TimeOffsetの単位は資料の推測ではなく公式の `ntohs(block.time_offset) * 1e-6` に従いました。
IMUの `ntohl` とビット列からfloatへの変換は `struct.unpack_from('>6f', ...)` に相当します。
公式manualを別途取得しての照合は未実施です。

## 公開PCAP解析

詳細: [validation_pcap.json](validation_pcap.json)。

| 指標 | 値 |
|---|---:|
| capture packets / MSOP / valid | 14,184 / 14,184 / 14,184 |
| invalid / DIFOP | 0 / 0 |
| payload長 | 全て1,200 bytes |
| frames / partial | 50 / 2 |
| points（ゼロ距離含む） | 1,361,664 |
| 非ゼロ距離点 | 1,110,206 |
| raw距離範囲 | 0–29.415 m |
| XYZのNaN / Inf | 0 / 0 |
| 観測sequence gap / duplicate / order anomaly | 2 / 0 / 0 |

先頭フレームは258 packets / 24,768 points。sequence 28の次が31で、途中開始と欠落を検出しました。
内部48フレームは各288 packets / 27,648 points。末尾は102 packets / 9,792 pointsでpartialです。
288という個数は復元後の観測結果であり、境界の固定長分割には使用していません。

PCAP capture時刻: `1770316586.980631`–`1770316591.905034`。
LiDAR point時刻: `69423.708223`–`69428.634604`。
両時計のepoch・同期は不明です。capture時刻による上書きや補正はしていません。
距離の妥当性検査はデータセットの回帰検査であり、実世界の校正精度の検証ではありません。

## 公式rs_driverとの実行比較

[scripts/rs_reference.cpp](scripts/rs_reference.cpp) は公式ヘッダーを変更せずincludeし、
`DecoderRSE1<PointCloudT<PointXYZIRT>>::processMsopPkt` に全payloadを順番に入力します。
Pythonの復号ロジックをC++へ転記して正解扱いする方式ではありません。

設定: `use_lidar_clock=true`、`dense_points=false`、座標transform無効、既定距離範囲0–200 m。
パケットごとの点列とsplit callbackのframe indexをバイナリに出力します。
EOFの残余もPython比較側で1フレームとして数えます。

結果: [validation_reference.json](validation_reference.json)。

| 比較 | 結果 |
|---|---|
| 対象 | 全14,184 packets / 全1,361,664 points / 全50 frame groups |
| 点数 | 各packet 96点、一致 |
| XYZ最大絶対誤差 | **0.0 m** |
| intensity | 完全一致 |
| timestamp最大絶対誤差 | **0.0 s** |
| 全packetのframe index | 完全一致 |
| 公式距離判定の範囲外 | 0点 |

判定許容誤差はXYZ `rtol=2e-7, atol=1e-6 m`、timestamp `rtol=0, atol=1e-9 s`。
今回の実測差は許容幅内というだけでなく0です。

### 意図した挙動差

公式は既定で0–200 mの範囲判定を行い、範囲外をNaN化、またはdense設定では除外します。
本デコーダはユーザー要件に従い、範囲外でもraw値からXYZを出力します。
合成試験で200 m超・intensity 0を保持することを確認しました。実測PCAPには該当範囲外点がありません。

`complete`・不完全理由はPython側で追加した品質情報であり、公式出力との比較対象ではありません。
フレーム境界自体は公式と同じです。大きな欠落や順序異常では複数の実フレームが結合されたり、
一つの実フレームが分割されたりする可能性があります。sequenceだけでは完全に解消できません。
その場合のduplicate集計は同一組立フレーム内のsequence重複であり、UDPの重複配送を証明しません。

## UDP・保存・合成試験

- 等速replay: 14,184送信 / 14,184受信、欠落0。50フレーム、partial 2。全NPZフィールドがofflineと一致。
- 最大速度replay（最新回帰試験）: 14,184送信 / 8,363受信、5,821欠落。この実行では41組立フレーム、partial 24。無欠落は保証しません。
- 数値は実行環境・負荷によって変わります。[等速記録](validation_udp_rate_1.json)、[最大速度記録](validation_udp_rate_0.json)。
- NPZ全フィールドとPCDの保存・再読込を試験しました。
- 参照PythonとNumPy版は境界値および100個のランダムblock列で一致しました。
- 合成DIFOPの1,2,3,4,5,6は完全一致。逆endian、長さ異常、magic異常、時刻を試験しました。
- live受信に不正MSOPと合成DIFOPを送信し、処理継続・6値・ホスト受信時刻の分離を確認しました。

## Open3Dリアルタイム描画の追加検証

Open3D 0.19.0 / Windows x86_64で実ウィンドウを作成し、公開PCAPをlocalhostへ等速再送しました。
共通 `live.receive` → `Pipeline` → 最新フレーム1個のmailbox → メインスレッドのOpen3D描画で検証しています。

- 14,184送信 / 14,184受信、全50フレームを描画、表示待ちによる置換0。
- XYZ native座標を維持。最終描画画像（PCAP末尾のpartial frame）を目視確認しました。
- 検証画像: [docs/validation/viewer_smoke.png](docs/validation/viewer_smoke.png)。統計: [docs/validation/viewer_smoke.json](docs/validation/viewer_smoke.json)。
- 描画が遅い場合は表示待ちを置換するため、描画数は環境・負荷で変わります。
- 自動試験でmailboxの容量制限、表示変換の非破壊性、Open3D実geometry変換、受信エラー時のウィンドウ終了を確認しました。
- 既存の公式比較・offline・UDP・IMU試験も通過しました。
- 実機E1R入力、JetsonでのOpen3D表示は未検証です。

## Remaining issues / UNKNOWN

IMU physical units / axis convention / calibration、実DIFOP、firmware差異、時計同期、reserved領域の意味は未検証です。
**physical unit is not yet verified**。
IMU状態: **IMPLEMENTED / SYNTHETICALLY TESTED / NOT VALIDATED WITH REAL DIFOP**。
Ubuntu 22.04 / aarch64 / Jetson Orinでの動作・性能、実機NIC経由の受信はNOT VALIDATEDです。
最大速度での欠落があるため、実機帯域での性能は対象機上で別途計測してください。
