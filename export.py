import os
import json
import hashlib
from google.cloud import bigquery

# 環境変数から取得
PROJECT_ID = os.environ.get("BQ_PROJECT_ID", "youtube-vocaloid-song-trackar")
DATASET_ID = os.environ.get("BQ_DATASET_ID", "data")
OUTPUT_DIR = "logs"
TOTAL_GROUPS = 50  # song.html / チャート用時系列ログの分割数

def get_group_index(video_id: str, total_groups: int = TOTAL_GROUPS) -> int:
    """video_idのハッシュ値から0〜(total_groups-1)のグループインデックスを決定 (JSと完全一致)"""
    if not video_id:
        return 0
    
    hash_int = 0
    for char in video_id:
        # JavaScriptの (hash << 5) - hash + charCodeAt(i) と同等の計算
        hash_int = ((hash_int << 5) - hash_int + ord(char)) & 0xFFFFFFFF
    
    # 符号付き32bit整数に変換（JSの `hash |= 0` と一致させる）
    if hash_int & 0x80000000:
        hash_int = -((~hash_int & 0xFFFFFFFF) + 1)
        
    return abs(hash_int) % total_groups

def datetime_serializer(obj):
    """日時オブジェクトのJSONシリアライズ対策"""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def export_table_to_single_json(client: bigquery.Client, query: str, filename: str, label: str):
    """単一のサマリーJSONを logs ディレクトリにエクスポートする汎用関数"""
    print(f"📦 [{label}] データの取得中...")
    query_job = client.query(query)
    rows = query_job.result()
    
    data = []
    for row in rows:
        row_dict = dict(row.items())
        # 日付フォーマットの調整
        for k, v in row_dict.items():
            if hasattr(v, 'isoformat'):
                row_dict[k] = v.isoformat()
        data.append(row_dict)
        
    # 🌟 修正: 確実に logs フォルダ内に保存するようにパスを結合
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, filename)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ [{label}] 保存完了 ({len(data)} 件) -> {output_path}")

def export_grouped_logs(client: bigquery.Client, query: str, file_prefix: str, label: str):
    """50グループにハッシュ分散して logs ディレクトリに書き出す汎用関数"""
    print(f"📦 [{label}] 50グループ分割データの取得中...")
    query_job = client.query(query)
    rows = query_job.result()
    
    # 50グループ分のバッファを用意
    groups_data = {i: {} for i in range(TOTAL_GROUPS)}
    count = 0
    
    for row in rows:
        row_dict = dict(row.items())
        vid = row_dict.get("video_id")
        if not vid:
            continue
            
        for k, v in row_dict.items():
            if hasattr(v, 'isoformat'):
                row_dict[k] = v.isoformat()
                
        group_idx = get_group_index(vid)
        if vid not in groups_data[group_idx]:
            groups_data[group_idx][vid] = []
        groups_data[group_idx][vid].append(row_dict)
        count += 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for i in range(TOTAL_GROUPS):
        file_path = os.path.join(OUTPUT_DIR, f"{file_prefix}_{i}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(groups_data[i], f, ensure_ascii=False)
            
    print(f"✅ [{label}] 50グループ出力完了 (全 {count} 行) -> {file_prefix}_0.json 〜 {file_prefix}_{TOTAL_GROUPS-1}.json (in {OUTPUT_DIR}/)")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = bigquery.Client(project=PROJECT_ID)
    
    print("🚀 [VocaTracker Export] GitHub Actions バッチ処理を開始します...")
    
    # 1. ランキングサマリー (ranking.html 用)
    query_rankings = f"""
        SELECT video_id, title, total_views, increase_yesterday, increase_7d, increase_30d,
               rank_total, rank_yesterday, rank_7d, rank_30d,
               rank_change_total, rank_change_yesterday, rank_change_7d, rank_change_30d, updated_at
        FROM `{PROJECT_ID}.{DATASET_ID}.t_rankings_summary`
    """
    export_table_to_single_json(client, query_rankings, "rankings.json", "ランキングサマリー")

    # 2. 真のバズレーダー (buzz.html / 注目の楽曲ページ用)
    query_buzz = f"""
        SELECT video_id, title, display_title, mr, views_inc_24h, likes_inc_24h, lrm_score, buzz_category, updated_at
        FROM `{PROJECT_ID}.{DATASET_ID}.t_true_buzz_radar`
    """
    export_table_to_single_json(client, query_buzz, "buzz_radar.json", "バズレーダー")

    # 3. 新曲レーダー (newrelease.html / 注目の楽曲ページ用)
    query_new_release = f"""
        SELECT video_id, title, display_title, current_views, current_likes, video_age_days, total_like_rate_pct, new_release_category, updated_at
        FROM `{PROJECT_ID}.{DATASET_ID}.t_new_release_radar`
    """
    export_table_to_single_json(client, query_new_release, "new_release.json", "新曲レーダー")

    # 4. マイルストーン到達ステータス・予測 (forecast.html / マイルストーンログ用)
    query_milestone_status = f"""
        SELECT video_id, title, current_views, next_target, target_order, target_label, views_remaining, hourly_speed, days_to_reach, sort_minutes, estimated_achieved_at, latest_updated_at_jst
        FROM `{PROJECT_ID}.{DATASET_ID}.t_milestones_status`
    """
    export_table_to_single_json(client, query_milestone_status, "milestones_status.json", "大台予測ステータス")

    # 5. マイルストーン達成履歴 (archive.html / マイルストーンログ用)
    query_milestone_history = f"""
        SELECT video_id, title, display_title, achieved_views, milestone_label, milestone_order, achieved_date, achieved_datetime, sort_timestamp_num
        FROM `{PROJECT_ID}.{DATASET_ID}.t_milestones_history`
    """
    export_table_to_single_json(client, query_milestone_history, "milestones_history.json", "大台達成アーカイブ")

    # 6. 全曲検索・メタデータ用サマリー (search.html / index.html 用)
    query_songs_summary = f"""
        SELECT video_id, title, display_title, views, hourly_inclease, like_count, published_at, updated_at
        FROM `{PROJECT_ID}.{DATASET_ID}.t_hourly_logs_30d`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY video_id ORDER BY updated_at DESC) = 1
    """
    export_table_to_single_json(client, query_songs_summary, "songs_summary.json", "全曲検索サマリー")

    # 7. 楽曲詳細ページ用・30日ログ (song.html 用・50グループ分割)
    query_hourly_logs = f"""
        SELECT video_id, title, display_title, views, hourly_inclease, like_count, published_at, updated_at
        FROM `{PROJECT_ID}.{DATASET_ID}.t_hourly_logs_30d`
        ORDER BY updated_at DESC
    """
    export_grouped_logs(client, query_hourly_logs, "song_group", "楽曲30日ログ")

    # 8. マイルストーン予測チャート用統合データ (マイルストーンログ/予測グラフ用・50グループ分割)
    query_chart_combined = f"""
        SELECT video_id, title, log_time, actual_views, predicted_views, chart_min_views, chart_max_views
        FROM `{PROJECT_ID}.{DATASET_ID}.t_milestone_chart_combined`
        ORDER BY log_time ASC
    """
    export_grouped_logs(client, query_chart_combined, "chart_group", "マイルストーン予測チャート")

    print("🎉 すべてのエクスポート処理が正常に完了しました！")

if __name__ == "__main__":
    main()
