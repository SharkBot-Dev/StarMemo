# 星空メモ
⭐星空型のメモ超

# 主な特徴
・同じようなワードのメモが正座としてつながる。<br>
・メモをほかの人に共有できる<br>
・同じようなメモを書いている人に自分のメモを見せられる<br>
・ユーザーごとにメモを投稿できる<br>
・公開するかしないかを選べる<br>
・自己ホストできる<br>
・3つのデータベースに対応: MongoDB / SQLite / PostgreSQL

## データベース
環境変数 `DB_TYPE` で切り替えられます。
| DB_TYPE | データベース | 備考 |
|---------|------------|---------|
| `mongodb`（デフォルト） | MongoDB | デフォルト |
| `sqlite` | SQLite | 追加インストール不要！ 一番お手軽！ |
| `postgresql` | PostgreSQL | postrgresqlを使いたい方におすすめ！ |

どのデータベースを選んでも、機能や操作に違いはありません。

# 自己ホストの手順

### 必要環境

・Python 3.14 以上
・必要なライブラリ（`requirements.txt`）

### インストール

1. このレポジトリをフォークし、フォーク後のレポジトリをクローンする
2. クローン後にvenvを作成し、requirements.txtの内容をインストールする
3. example.envを.envに改名し、適切に内容を入力する
#### `.env` 設定例

**SQLite（もっともお手軽）:**
```env
DB_TYPE=sqlite
SECREST_KEY=ランダムな文字列
TURNSTILE_SECRET=
TURNSTILE_SITEKEY=
TITLE=星空メモ
DESCRIPTION=星空にメモを追加できる新感覚メモサービス
```

**MongoDB:**
```env
DB_TYPE=mongodb
MONGO_URI=mongodb://localhost:27017
DB_NAME=NotSNS
SECREST_KEY=ランダムな文字列
TURNSTILE_SECRET=...
TURNSTILE_SITEKEY=...
```

**PostgreSQL:**
```env
DB_TYPE=postgresql
POSTGRESQL_URL=postgresql://user:pass@localhost:5432/notsns
SECREST_KEY=ランダムな文字列
TURNSTILE_SECRET=...
TURNSTILE_SITEKEY=...
```

4. 「terms.html」と、「privacy.html」を適切な利用規約に差し替える
5. main.pyを起動する
6. localhost:5000にアクセスし、ログインページが表示されればOK

### 管理者の作成

1. ブラウザでログイン（初回アクセス時に自動的にアカウント作成）
2. MongoDB の場合: `Users` コレクションで自分の `roles` に `"owner"` を追加
3. SQLite/PostgreSQL の場合: `documents` テーブルで `collection='users'` のドキュメントの `data->roles` に `"owner"` を追加
4. 管理画面（`/admin`）からロールやユーザーを管理できます

# 権限システム
星空メモには権限システムとロールシステムがあり、管理者ページから追加できます。<br>
また、権限IDは以下のものがあります。
1. 投稿の閲覧
2. 投稿の作成
3. 投稿の削除
4. メンバーのミュート
5. メンバーのBan
6. ロール管理

# メンバーの処罰について
星空メモでユーザーを処罰をするには、以下のロールを追加することで処罰できます。<br>
Banの場合: 「ban」<br>
ミュートの場合: 「mute」

# 自分専用メモにする方法
星空メモを自分専用にするには、「user」ロールの権限を「1」だけに絞り、<br>
「owner」ロールをMongoDBから自分に追加れば自分専用にできます。

## パスワードポリシー

・新規登録時: 8文字以上必要
・パスワード変更時: 同様に8文字以上必須
・パスワード変更はログイン後のフッターリンクから行えます