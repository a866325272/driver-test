# 汽車筆試題庫練習

1090 題汽車筆試題庫的抽題練習 web app。還沒練過、或常答錯的題目會比較容易被抽到。

- 練習頁 `/driver-test`：可以選擇範圍（全部，或架構一、二、三），作答後馬上顯示對錯
- 統計頁 `/driver-test/stats`：覆蓋率、各架構答對率、每題的練習次數、答對率和目前的抽中機率

## 本機執行

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py            # http://localhost:5000/driver-test
```

作答紀錄預設存在 `var/progress.db`，可以用環境變數 `PROGRESS_DB` 改成其他路徑。

## Docker

```bash
docker build -t driver-test:latest .
docker compose up -d                # http://localhost:8000/driver-test
```

`docker-compose.yml` 會把 host 的 `./progress` mount 到 container 的 `/data`，作答紀錄
`progress.db` 存在這裡，所以重建 container 也不會遺失。容器內以 uid 1000 執行，
Linux host 上如果寫入被拒，先執行 `mkdir -p progress && sudo chown 1000:1000 progress`。

## 路徑與 reverse proxy

所有路徑都在 `/driver-test` 底下，proxy 設一條 prefix 規則就能涵蓋（nginx、Kubernetes Ingress `pathType: Prefix` 都適用）：

| 路徑 | 用途 |
|---|---|
| `/driver-test` | 練習頁 |
| `/driver-test/stats` | 統計頁 |
| `/driver-test/api/...` | API |
| `/driver-test/static/...` | CSS、JS、題目圖片 |

`/` 和 `/driver-test/` 會轉址到 `/driver-test`。nginx 範例（注意 `proxy_pass` 後面不要加路徑，才會原樣保留 prefix）：

```nginx
location /driver-test {
    proxy_pass http://127.0.0.1:8000;
}
```

## 抽題權重

`sampler.py`：

```
權重 = 久未練習加成 × 錯誤率加成，最近 20 次練過的題目暫時不抽
久未練習加成 = 1 + min(age, 1000) / 100      age = 距離上次練這題又練了幾題
                                             沒練過的題目 age = 總練習次數 + 100，且不設上限
錯誤率加成   = 4 × (0.1 + 錯誤率)²             錯誤率 = (答錯 + 1) / (作答 + 2)
```

參數集中在 `sampler.py` 檔案開頭。

## 測試

```bash
./venv/bin/python -m unittest discover -s tests
```

`tests/test_sampler.py` 模擬作答 3000 次，驗證覆蓋率、答錯題目的加權、冷卻和範圍。
`tests/test_app.py` 用 Flask test client 測 API。兩者都只寫暫存目錄，不會動到 `var/progress.db`。

## 重新產生題庫

題庫已經轉好放在 `data/questions.json` 和 `static/img/`，原始 PDF 在 `source/`。
如果題庫 PDF 改版了，把新的 PDF 放進 `source/` 後重新解析：

```bash
./venv/bin/pip install -r tools/requirements.txt
./venv/bin/python -I tools/parse_pdf.py source/<題庫.pdf> .
```

## 題庫來源

`source/汽車筆試題庫_公告115.06.9.pdf` 為公開的汽車筆試題庫（檔名標示公告 115.06.9，內文版本 115.5.29）。
來源：<!-- TODO 補上官方下載頁網址 -->
依著作權法第 9 條第 1 項第 5 款，依法令舉行之各類考試試題不得為著作權之標的。
本專案的程式碼與題庫轉換結果僅供練習使用。

## 重置紀錄

停止服務後刪除 `progress.db` 即可（本機是 `var/progress.db`，Docker 是 `progress/progress.db`）。
