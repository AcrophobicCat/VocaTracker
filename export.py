import os
import json
from google.cloud import bigquery

# 環境変数から取得
PROJECT_ID = os.environ.get("BQ_PROJECT_ID")
DATASET_ID = os.environ.get("BQ_DATASET_ID")
TOTAL_PARTS = 500
OUTPUT_DIR = "logs"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = bigquery.Client(project=PROJECT_ID)
    
    print(f"🚀 [GitHub Actions] 全 {TOTAL_PARTS} パーツのエクスポートを開始します...")
    
    for part_index in range(TOTAL_PARTS):
        print(f"📦 パート [{part_index} / {TOTAL_PARTS - 1}] 取得中...")
        
        query = f"""
            SELECT video_id, title, display_title, views, hourly_inclease, like_count, published_at, updated_at 
            FROM `{PROJECT_ID}.{DATASET_ID}.t_hourly_logs_30d`
            WHERE ABS(MOD(FARM_FINGERPRINT(video_id), {TOTAL_PARTS})) = {part_index}
            ORDER BY updated_at DESC
        """
        
        query_job = client.query(query)
        rows = query_job.result()
        
        part_data = []
        for row in rows:
            row_dict = dict(row.items())
            # 日時型などのシリアライズ対策が必要な場合はここで文字列化
            for k, v in row_dict.items():
                if hasattr(v, 'isoformat'):
                    row_dict[k] = v.isoformat()
            part_data.append(row_dict)
            
        file_path = os.path.join(OUTPUT_DIR, f"vocaloid_logs_part_{part_index}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(part_data, f, ensure_ascii=False, indent=2)
            
    print("🎉 すべてのパーツのファイル生成が完了しました！")

if __name__ == "__main__":
    main()
