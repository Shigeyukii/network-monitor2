# network-monitor2
# [200~バックエンド: Python + FastAPI

非同期ポーリングループ（APScheduler）
Ping監視: icmplib または subprocess
SNMP: pysnmp
DB: SQLite（セットアップ不要）
フロントエンド: HTML + Vanilla JS + Chart.js（CDN）

ビルドステップ不要でシンプルに動作
ディレクトリ構成:


network-monitor2/
├── backend/
│   ├── main.py        # FastAPI + ポーリング起動
│   ├── database.py    # SQLite定義
│   ├── poller.py      # Ping/SNMPポーリング
│   └── router/
│       ├── devices.py # デバイスCRUD API
│       └── metrics.py # メトリクス取得API
├── frontend/
│   ├── index.html     # ダッシュボード
│   └── static/
│       ├── app.js
│       └── style.css
└── requirements.txt
主な機能:

デバイス登録（IPアドレス、SNMPコミュニティ文字列など）
Ping死活監視（60秒間隔）、ダッシュボードで状態表示
SNMP対応機器のトラフィックグラフ（5分間隔、Chart.js）
稼働率・応答時間の履歴表示~
