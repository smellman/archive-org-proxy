# archive-org-proxy

`archive.org` 及びそのサブドメインに対するシンプルなプロキシサーバー。CORS ヘッダーを付与し、`Range` リクエストを透過的に転送します。

## 使い方

### Docker Compose で起動

```sh
docker compose up -d
```

ホストの `18080` 番ポートでリッスンします（`docker-compose.yml` 参照）。

### Docker で起動

```sh
docker build -t archive-org-proxy .
docker run -p 18080:80 archive-org-proxy
```

### ローカル開発で起動

[uv](https://docs.astral.sh/uv/) が必要です。

```sh
uv sync
uv run fastapi dev main.py
```

## エンドポイント

```
GET /proxy/{host}/{path}
```

- `{host}` は `archive.org` で終わるホスト名のみ許可されます（それ以外は `403` を返します）。
- `{path}` は転送先のパス・クエリ文字列です。
- リクエストの `Range` ヘッダーはそのまま転送され、レスポンスの `Content-Range` / `Accept-Ranges` も透過します。

### 例

`https://archive.org/details/example` を取得する場合:

```sh
curl http://localhost:18080/proxy/archive.org/details/example
```

`https://ia800000.us.archive.org/path/to/file` を部分取得する場合:

```sh
curl -H "Range: bytes=0-1023" \
  http://localhost:18080/proxy/ia800000.us.archive.org/path/to/file
```
