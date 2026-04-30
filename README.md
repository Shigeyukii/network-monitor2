# Network Monitor

Webブラウザで確認できるネットワーク監視アプリケーションです。  
Ping による死活監視と SNMP によるトラフィック監視をグラフで可視化します。

---

## 機能

| 機能 | 説明 |
|---|---|
| Ping 死活監視 | 定期的に Ping を送信し、UP / DOWN をリアルタイム表示 |
| SNMP トラフィック監視 | インターフェースごとの送受信トラフィックをグラフ表示 |
| ダッシュボード | 全デバイスの稼働状況を一覧表示（30 秒自動更新） |
| 詳細ビュー | Ping 応答時間グラフ・稼働率バー・トラフィックグラフ |
| 期間フィルター | 1 時間 / 6 時間 / 24 時間 / 3 日 / 7 日 |
| デバイス管理 | デバイスの追加・編集・削除 |
| 監視間隔変更 | Ping・SNMP の間隔を Web 画面から変更・即時反映 |
| 自動データクリーンアップ | Ping 結果: 7 日間 / SNMP トラフィック: 30 日間保持 |

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
│   ├── main.py          # FastAPI アプリ・スケジューラー起動
│   ├── database.py      # SQLite 初期化・接続管理
│   ├── poller.py        # Ping / SNMP ポーリング実装
│   ├── scheduler.py     # APScheduler ラッパー
│   └── router/
│       ├── devices.py   # デバイス CRUD API
│       ├── metrics.py   # メトリクス取得 API
│       └── settings.py  # 監視設定 API
├── frontend/
│   ├── index.html       # SPA（シングルページアプリ）
│   └── static/
│       ├── app.js       # フロントエンドロジック
│       └── style.css    # スタイルシート
├── data/
│   └── monitor.db       # SQLite データベース（自動生成）
└── requirements.txt     # Python 依存パッケージ
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
| Ping 間隔（秒） | このデバイスの Ping 間隔（デフォルト: 60 秒） |
| SNMP を有効にする | SNMP 対応機器の場合はオン |
| コミュニティ文字列 | SNMP コミュニティ名（デフォルト: public） |
| ポート | SNMP ポート番号（デフォルト: 161） |
| SNMP バージョン | v2c（推奨）または v1 |

### 監視間隔の変更

1. 画面右上の **「⚙ 設定」** をクリック
2. Ping 間隔・SNMP 間隔（秒）を入力
3. **「保存して適用」** をクリック（即時反映）

### 詳細ビュー

デバイスカードをクリックすると詳細ビューが開きます。

- **稼働率バー**: 選択期間の UP / DOWN の割合を視覚化
- **Ping 応答時間グラフ**: 時系列での RTT と UP / DOWN 状態
- **トラフィックグラフ**: インターフェースごとの送受信 bps（SNMP 有効時）

---

## API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/devices` | デバイス一覧取得 |
| POST | `/api/devices` | デバイス追加 |
| PUT | `/api/devices/{id}` | デバイス更新 |
| DELETE | `/api/devices/{id}` | デバイス削除 |
| GET | `/api/metrics/ping/{id}` | Ping 履歴取得 |
| GET | `/api/metrics/traffic/{id}` | トラフィックデータ取得 |
| GET | `/api/metrics/summary` | ダッシュボード集計 |
| GET | `/api/settings` | 監視設定取得 |
| PUT | `/api/settings` | 監視設定更新 |
| POST | `/api/settings/reschedule` | スケジューラー再設定 |

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
| SNMP トラフィック監視 | UDP 161（監視対象機器へ） |
| Web UI アクセス | TCP 8000（監視サーバー側） |

---

## データベース

SQLite を使用しており、追加のデータベースサーバーは不要です。  
データは `data/monitor.db` に自動保存されます。

| テーブル | 内容 | 保持期間 |
|---|---|---|
| devices | 登録デバイス情報 | 無期限 |
| ping_results | Ping 結果履歴 | 7 日間 |
| snmp_interfaces | インターフェース情報 | 無期限 |
| snmp_traffic | トラフィック履歴 | 30 日間 |
| settings | 監視設定 | 無期限 |

---

## 技術スタック

| 種別 | 技術 |
|---|---|
| バックエンド | Python + FastAPI |
| データベース | SQLite |
| SNMP ライブラリ | puresnmp |
| スケジューラー | APScheduler |
| フロントエンド | Vanilla JS + Chart.js |
| グラフ | Chart.js 4.x + chartjs-adapter-date-fns |
