# Network Monitor

Webブラウザで確認できるネットワーク監視アプリケーションです。  
Ping 死活監視・SNMP トラフィック監視・TCP ポート監視をグラフで可視化し、障害発生時には Teams / Slack へ自動通知します。  
ネットワーク構成を星座風マップで可視化する機能も備えています。

---

## 機能一覧

### 監視

| 機能 | 説明 |
|---|---|
| Ping 死活監視 | 定期的に Ping を送信し、UP / DOWN をリアルタイム表示 |
| TCP ポート監視 | 任意のポートへ TCP 接続チェック（HTTP・SSH など複数登録可） |
| SNMP トラフィック監視 | インターフェースごとの送受信トラフィックをグラフ表示（v1 / v2c） |

### アラート・通知

| 機能 | 説明 |
|---|---|
| アラート検知 | UP→DOWN / DOWN→UP の状態遷移時のみアラートを生成 |
| アラートパネル | ベルアイコンに未読バッジ表示・右スライドパネルで確認・既読化 |
| Teams 通知 | 障害・復旧を Microsoft Teams チャンネルへ Webhook 送信 |
| Slack 通知 | 障害・復旧を Slack チャンネルへ Webhook 送信 |
| 通知タイミング設定 | DOWN 検知時・復旧時をそれぞれ ON/OFF で切替可 |

### ダッシュボード・表示

| 機能 | 説明 |
|---|---|
| ダッシュボード | 全デバイスの稼働状況を一覧表示（30 秒自動更新） |
| デバイスグループ | グループを作成してデバイスを分類・フィルター表示 |
| 詳細ビュー | Ping 応答時間グラフ・稼働率バー・ポート状態・トラフィックグラフ |
| 期間フィルター | 1 時間 / 6 時間 / 24 時間 / 3 日 / 7 日 |
| 稼働率レポート | 1 時間 / 24 時間 / 7 日 / 30 日の稼働率を一覧表示・CSV エクスポート |

### ネットワークマップ

| 機能 | 説明 |
|---|---|
| 星座風マップ | デバイスを星に見立てて夜空に配置、接続線で構成を可視化 |
| 状態で色分け | UP=青白・DOWN=赤・Unknown=暗灰 |
| トラフィック連動 | SNMP トラフィックが多いほど星が大きく金色に輝く |
| 瞬きアニメーション | 全星が固有のリズムで瞬く、接続線は流れるダッシュアニメーション |
| ドラッグ配置 | 星をドラッグして自由に配置・位置は自動保存 |
| 接続線管理 | 任意のデバイス間に接続線を追加・削除 |

### 管理

| 機能 | 説明 |
|---|---|
| デバイス管理 | デバイスの追加・編集・削除 |
| 監視間隔変更 | Ping・SNMP の間隔を Web 画面から変更・即時反映 |
| 設定のバックアップ・復元 | デバイス・グループ・ポート設定を JSON でエクスポート／インポート |
| 自動データクリーンアップ | Ping / ポート結果: 7 日間 / SNMP トラフィック: 30 日間保持 |

---

## 動作環境

- Python 3.10 以上（開発環境: Python 3.14）
- Ubuntu / Debian 系 Linux（Windows でも動作可）
- ブラウザ: Chrome / Firefox / Edge（モダンブラウザ全般）

---

## ディレクトリ構成

```
network-monitor2/
├── backend/
│   ├── main.py              # FastAPI アプリ・スケジューラー起動
│   ├── database.py          # SQLite 初期化・接続管理
│   ├── poller.py            # Ping / TCP ポート / SNMP ポーリング実装
│   ├── notifier.py          # Teams / Slack Webhook 通知
│   ├── scheduler.py         # APScheduler ラッパー
│   └── router/
│       ├── devices.py       # デバイス CRUD API
│       ├── groups.py        # グループ CRUD API
│       ├── ports.py         # TCP ポート監視 API
│       ├── metrics.py       # メトリクス取得 API
│       ├── alerts.py        # アラート API
│       ├── reports.py       # 稼働率レポート API
│       ├── importexport.py  # 設定インポート・エクスポート API
│       ├── networkmap.py    # ネットワークマップ API
│       └── settings.py      # 監視設定 API
├── frontend/
│   ├── index.html           # SPA（シングルページアプリ）
│   └── static/
│       ├── app.js           # フロントエンドロジック
│       ├── map.js           # 星座風マップ Canvas レンダラー
│       └── style.css        # スタイルシート
├── data/
│   └── monitor.db           # SQLite データベース（自動生成）
└── requirements.txt         # Python 依存パッケージ
```

---

## セットアップ

### 1. ファイルの取得

```bash
# git を使う場合
git clone <リポジトリURL>
cd network-monitor2

# フォルダをコピーする場合はそのまま配置
```

### 2. pip のインストール（未インストールの場合）

```bash
curl -sS https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages
```

### 3. 依存パッケージのインストール

```bash
python3 -m pip install -r requirements.txt --break-system-packages
```

主な依存パッケージ:

| パッケージ | 用途 |
|---|---|
| fastapi | Web フレームワーク |
| uvicorn | ASGI サーバー |
| puresnmp | SNMP ポーリング（Python 3.10+ 対応） |
| apscheduler | 定期実行スケジューラー |

---

## 起動

```bash
cd network-monitor2/backend
python3 main.py
```

起動後、ブラウザで以下にアクセスします。

```
http://localhost:8000
```

別端末からアクセスする場合:

```
http://<サーバーの IP アドレス>:8000
```

---

## 使い方

### デバイスの追加

1. 画面右上の **「＋ デバイス追加」** ボタンをクリック
2. 以下の項目を入力して **「追加」**

| 項目 | 説明 |
|---|---|
| デバイス名 | 任意の識別名（例: Core-Switch-01） |
| IP アドレス | 監視対象の IP アドレス |
| グループ | 所属グループ（任意） |
| Ping 間隔（秒） | このデバイスの Ping 間隔（デフォルト: 60 秒） |
| SNMP を有効にする | SNMP 対応機器の場合はオン |
| コミュニティ文字列 | SNMP コミュニティ名（デフォルト: public） |
| ポート | SNMP ポート番号（デフォルト: 161） |
| SNMP バージョン | v2c（推奨）または v1 |

### グループ管理

1. 画面右上の **「🗂 グループ管理」** をクリック
2. グループ名とカラーを選んで **「追加」**
3. ダッシュボードのタブでグループ別にフィルター表示できます

### TCP ポート監視の追加

1. デバイスカードをクリックして詳細ビューを開く
2. **「TCP ポート監視」** セクションでポート番号・ラベルを入力して **「追加」**
3. 次のポーリングから状態（OPEN / CLOSED）が表示されます

### アラートの確認

- 障害発生・復旧時にヘッダーのベルアイコン🔔に未読バッジが表示されます
- クリックするとアラートパネルが開き、履歴を確認・既読化できます

### 稼働率レポート

1. 画面右上の **「📊 レポート」** をクリック
2. 全デバイスの 1 時間 / 24 時間 / 7 日 / 30 日の稼働率を確認できます
3. **「⬇ CSV ダウンロード」** で Excel 用のファイルを取得できます

### 通知設定（Teams / Slack）

1. **「⚙ 設定」** をクリック
2. Teams または Slack の Webhook URL を入力
3. **「テスト送信」** で疎通確認
4. **「保存して適用」** で反映

#### Webhook URL の取得方法

**Microsoft Teams:**
1. 通知先チャンネルを右クリック → コネクタ
2. **Incoming Webhook** を追加 → 名前を入力 → URL をコピー

**Slack:**
1. [api.slack.com/apps](https://api.slack.com/apps) でアプリを作成
2. **Incoming Webhooks** を有効化 → チャンネルを選択 → URL をコピー

### 監視間隔の変更

1. **「⚙ 設定」** をクリック
2. Ping 間隔・SNMP 間隔（秒）を入力
3. **「保存して適用」** をクリック（即時反映）

### ネットワークマップの使い方

1. ヘッダーの **「🌌 マップ」** をクリック
2. 右側パネルの **「追加」** ボタンでデバイスを星としてマップに配置
3. 星をドラッグして自由に位置を調整（離すと自動保存）
4. **「🔗 接続を追加」** をクリックして接続モードに入り、繋ぎたい星を順にクリック
5. 星にホバーするとデバイス名・IP・RTT・トラフィックが表示
6. 星をクリックするとデバイス詳細ビューへ遷移

| 星の見た目 | 意味 |
|---|---|
| 青白い星 | UP（正常） |
| 金色の輝く星 | UP + 高トラフィック |
| 赤い星 | DOWN（障害） |
| 暗い星 | 状態不明 |
| 大きい星 | トラフィック量が多い |
| 流れる接続線 | UP デバイス間の接続 |

### 設定のバックアップ・復元

**エクスポート（バックアップ）:**
1. **「⚙ 設定」** → 「デバイス設定のバックアップ・復元」セクション
2. **「⬇ JSON をダウンロード」** でファイルを保存

**インポート（復元）:**
1. 同セクションの **「⬆ JSON を読み込む」** でファイルを選択
2. 自動的に登録が完了し、件数が表示される

> アプリのバージョンアップ時や別端末への移行時に便利です。  
> 同じ IP アドレスのデバイスはスキップされるため、重複登録の心配はありません。

---

## API エンドポイント

### デバイス

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/devices` | デバイス一覧取得 |
| POST | `/api/devices` | デバイス追加 |
| PUT | `/api/devices/{id}` | デバイス更新 |
| DELETE | `/api/devices/{id}` | デバイス削除 |

### グループ

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/groups` | グループ一覧取得 |
| POST | `/api/groups` | グループ追加 |
| PUT | `/api/groups/{id}` | グループ更新 |
| DELETE | `/api/groups/{id}` | グループ削除 |

### TCP ポート監視

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/devices/{id}/ports` | ポート一覧取得 |
| POST | `/api/devices/{id}/ports` | ポート追加 |
| DELETE | `/api/devices/{id}/ports/{port}` | ポート削除 |
| GET | `/api/devices/{id}/ports/history` | ポート結果履歴 |

### メトリクス

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/metrics/ping/{id}` | Ping 履歴取得 |
| GET | `/api/metrics/traffic/{id}` | トラフィックデータ取得 |
| GET | `/api/metrics/summary` | ダッシュボード集計 |

### アラート

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/alerts` | アラート一覧取得 |
| GET | `/api/alerts/unread-count` | 未読件数取得 |
| PUT | `/api/alerts/{id}/acknowledge` | 1 件既読化 |
| POST | `/api/alerts/acknowledge-all` | 全件既読化 |

### レポート

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/reports/uptime` | 稼働率レポート取得 |
| GET | `/api/reports/uptime/csv` | 稼働率 CSV ダウンロード |

### インポート・エクスポート

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/export` | 設定を JSON ファイルとしてダウンロード |
| POST | `/api/import` | JSON ファイルから設定を一括登録 |

### ネットワークマップ

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/map` | マップデータ取得（ノード・エッジ・未配置デバイス） |
| POST | `/api/map/nodes/{device_id}` | デバイスをマップに追加 |
| PUT | `/api/map/nodes/{device_id}` | ノード位置を更新 |
| DELETE | `/api/map/nodes/{device_id}` | デバイスをマップから削除 |
| POST | `/api/map/edges` | 接続線を追加 |
| DELETE | `/api/map/edges/{id}` | 接続線を削除 |

### 設定

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/settings` | 監視設定取得 |
| PUT | `/api/settings` | 監視設定更新 |
| POST | `/api/settings/reschedule` | スケジューラー再設定 |
| POST | `/api/settings/test-notify` | Webhook テスト送信 |

インタラクティブな API ドキュメントは起動後に以下で確認できます。

```
http://localhost:8000/docs
```

---

## 別端末への移行

`venv/` フォルダを除いたすべてのファイルをコピーし、新端末でセットアップ手順を実行します。

```bash
# rsync を使う場合（既存データは引き継がない）
rsync -av --exclude='venv/' --exclude='data/' network-monitor2/ user@new-host:~/network-monitor2/

# 既存データも引き継ぐ場合
rsync -av --exclude='venv/' network-monitor2/ user@new-host:~/network-monitor2/
```

新端末でも同じセットアップ手順（pip インストール → パッケージインストール）を実行してから起動します。

---

## ネットワーク要件

| 用途 | プロトコル / ポート |
|---|---|
| Ping 死活監視 | ICMP（監視対象機器へ） |
| TCP ポート監視 | TCP 任意ポート（監視対象機器へ） |
| SNMP トラフィック監視 | UDP 161（監視対象機器へ） |
| Web UI アクセス | TCP 8000（監視サーバー側） |

---

## データベース

SQLite を使用しており、追加のデータベースサーバーは不要です。  
データは `data/monitor.db` に自動保存されます。

| テーブル | 内容 | 保持期間 |
|---|---|---|
| devices | 登録デバイス情報 | 無期限 |
| groups | デバイスグループ情報 | 無期限 |
| ping_results | Ping 結果履歴 | 7 日間 |
| port_checks | TCP ポート監視設定 | 無期限 |
| port_results | TCP ポート結果履歴 | 7 日間 |
| snmp_interfaces | インターフェース情報 | 無期限 |
| snmp_traffic | トラフィック履歴 | 30 日間 |
| alerts | アラート履歴 | 無期限 |
| map_nodes | マップ上のノード位置 | 無期限 |
| map_edges | マップ上の接続線 | 無期限 |
| settings | 監視設定 | 無期限 |

---

## 技術スタック

| 種別 | 技術 |
|---|---|
| バックエンド | Python + FastAPI |
| データベース | SQLite |
| SNMP ライブラリ | puresnmp |
| スケジューラー | APScheduler |
| 通知 | urllib（標準ライブラリ）で Webhook POST |
| フロントエンド | Vanilla JS + Chart.js |
| グラフ | Chart.js 4.x + chartjs-adapter-date-fns |
| ネットワークマップ | HTML5 Canvas（requestAnimationFrame アニメーション） |
