#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ベッドコントロールシミュレーター用データベースマネージャー
おもろまちメディカルセンター AI ワークスペース

SQLiteでベッドコントロール関連データを永続化する
"""

import sqlite3
import pandas as pd
import json
import os
from datetime import datetime

# データベースファイルパス（スクリプトのディレクトリ基準で data/bed_control.db）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'bed_control.db')


def get_connection(db_path=None):
    """
    データベース接続を取得する

    Args:
        db_path (str, optional): データベースファイルパス。Noneの場合はデフォルトパス使用

    Returns:
        sqlite3.Connection: データベース接続オブジェクト
    """
    if db_path is None:
        db_path = DB_PATH

    try:
        # data ディレクトリが存在しなければ作成
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        conn = sqlite3.connect(db_path)
        # 外部キー制約を有効化
        conn.execute("PRAGMA foreign_keys = ON")

        # テーブルが存在しない場合は初期化
        init_tables(conn)

        return conn

    except Exception as e:
        print(f"データベース接続エラー: {e}")
        return None


def init_tables(conn):
    """
    テーブル初期化（存在しない場合のみ作成）

    Args:
        conn (sqlite3.Connection): データベース接続
    """
    try:
        cursor = conn.cursor()

        # daily_records テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_records (
                date TEXT NOT NULL,
                ward TEXT DEFAULT 'all',
                total_patients INTEGER,
                new_admissions INTEGER,
                discharges INTEGER,
                discharge_a INTEGER DEFAULT 0,
                discharge_b INTEGER DEFAULT 0,
                discharge_c INTEGER DEFAULT 0,
                phase_a_count INTEGER,
                phase_b_count INTEGER,
                phase_c_count INTEGER,
                avg_los REAL,
                notes TEXT,
                data_source TEXT DEFAULT 'manual',
                PRIMARY KEY (date, ward)
            )
        """)

        # abc_state テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS abc_state (
                key TEXT PRIMARY KEY,
                a_count REAL DEFAULT 0,
                b_count REAL DEFAULT 0,
                c_count REAL DEFAULT 0,
                updated_at TEXT
            )
        """)

        # day_buckets テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS day_buckets (
                key TEXT PRIMARY KEY,
                bucket_json TEXT,
                updated_at TEXT
            )
        """)

        # app_settings テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.commit()

    except Exception as e:
        print(f"テーブル初期化エラー: {e}")


def save_daily_records(df, db_path=None):
    """
    DataFrameをdaily_recordsテーブルに保存（REPLACE INTO で上書き）

    Args:
        df (pd.DataFrame): 日次記録データフレーム
        db_path (str, optional): データベースファイルパス
    """
    conn = get_connection(db_path)
    if conn is None:
        return

    try:
        # date列を文字列形式に変換
        df_copy = df.copy()
        if 'date' in df_copy.columns:
            df_copy['date'] = pd.to_datetime(df_copy['date']).dt.strftime('%Y-%m-%d')

        # REPLACE INTO で既存データを上書き
        df_copy.to_sql('daily_records', conn, if_exists='replace', index=False)
        conn.commit()
        print(f"日次記録を保存しました: {len(df_copy)}件")

    except Exception as e:
        print(f"日次記録保存エラー: {e}")
    finally:
        conn.close()


def load_daily_records(db_path=None):
    """
    daily_recordsテーブルからDataFrameを読み込み

    Args:
        db_path (str, optional): データベースファイルパス

    Returns:
        pd.DataFrame: 日次記録データフレーム。データがない場合は空のDataFrame
    """
    conn = get_connection(db_path)
    if conn is None:
        return _create_empty_daily_records()

    try:
        df = pd.read_sql_query("SELECT * FROM daily_records ORDER BY date, ward", conn)

        if df.empty:
            return _create_empty_daily_records()

        # date列をdatetime型に変換
        df['date'] = pd.to_datetime(df['date'])

        return df

    except Exception as e:
        print(f"日次記録読み込みエラー: {e}")
        return _create_empty_daily_records()
    finally:
        conn.close()


def _create_empty_daily_records():
    """
    空の日次記録DataFrameを作成

    Returns:
        pd.DataFrame: 空のデータフレーム
    """
    columns = [
        'date', 'ward', 'total_patients', 'new_admissions', 'discharges',
        'discharge_a', 'discharge_b', 'discharge_c',
        'phase_a_count', 'phase_b_count', 'phase_c_count',
        'avg_los', 'notes', 'data_source'
    ]
    return pd.DataFrame(columns=columns)


def save_abc_state(abc_state, db_path=None):
    """
    ABC状態辞書を保存

    Args:
        abc_state (dict): ABC状態 {"A": x, "B": y, "C": z}
        db_path (str, optional): データベースファイルパス
    """
    conn = get_connection(db_path)
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        current_time = datetime.now().isoformat()

        cursor.execute("""
            REPLACE INTO abc_state (key, a_count, b_count, c_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'current',
            abc_state.get('A', 0),
            abc_state.get('B', 0),
            abc_state.get('C', 0),
            current_time
        ))

        conn.commit()
        print("ABC状態を保存しました")

    except Exception as e:
        print(f"ABC状態保存エラー: {e}")
    finally:
        conn.close()


def load_abc_state(db_path=None):
    """
    ABC状態を読み込み

    Args:
        db_path (str, optional): データベースファイルパス

    Returns:
        dict: ABC状態辞書。データがない場合はNone
    """
    conn = get_connection(db_path)
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT a_count, b_count, c_count FROM abc_state WHERE key = ?", ('current',))
        row = cursor.fetchone()

        if row:
            return {
                'A': float(row[0]),
                'B': float(row[1]),
                'C': float(row[2])
            }
        return None

    except Exception as e:
        print(f"ABC状態読み込みエラー: {e}")
        return None
    finally:
        conn.close()


def save_day_buckets(day_buckets, db_path=None):
    """
    日齢バケットをJSON文字列で保存

    Args:
        day_buckets: 日齢バケットデータ
        db_path (str, optional): データベースファイルパス
    """
    conn = get_connection(db_path)
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        current_time = datetime.now().isoformat()
        bucket_json = json.dumps(day_buckets, ensure_ascii=False, indent=2)

        cursor.execute("""
            REPLACE INTO day_buckets (key, bucket_json, updated_at)
            VALUES (?, ?, ?)
        """, ('current', bucket_json, current_time))

        conn.commit()
        print("日齢バケットを保存しました")

    except Exception as e:
        print(f"日齢バケット保存エラー: {e}")
    finally:
        conn.close()


def load_day_buckets(db_path=None):
    """
    日齢バケットを読み込み

    Args:
        db_path (str, optional): データベースファイルパス

    Returns:
        日齢バケットデータ。データがない場合はNone
    """
    conn = get_connection(db_path)
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT bucket_json FROM day_buckets WHERE key = ?", ('current',))
        row = cursor.fetchone()

        if row and row[0]:
            return json.loads(row[0])
        return None

    except Exception as e:
        print(f"日齢バケット読み込みエラー: {e}")
        return None
    finally:
        conn.close()


def save_setting(key, value, db_path=None):
    """
    設定値を保存

    Args:
        key (str): 設定キー
        value (str): 設定値
        db_path (str, optional): データベースファイルパス
    """
    conn = get_connection(db_path)
    if conn is None:
        return

    try:
        cursor = conn.cursor()
        cursor.execute("""
            REPLACE INTO app_settings (key, value)
            VALUES (?, ?)
        """, (key, str(value)))

        conn.commit()
        print(f"設定を保存しました: {key} = {value}")

    except Exception as e:
        print(f"設定保存エラー: {e}")
    finally:
        conn.close()


def load_setting(key, db_path=None):
    """
    設定値を読み込み

    Args:
        key (str): 設定キー
        db_path (str, optional): データベースファイルパス

    Returns:
        str: 設定値。データがない場合はNone
    """
    conn = get_connection(db_path)
    if conn is None:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()

        if row:
            return row[0]
        return None

    except Exception as e:
        print(f"設定読み込みエラー: {e}")
        return None
    finally:
        conn.close()


def clear_all_data(db_path=None):
    """
    全テーブルのデータをクリア

    Args:
        db_path (str, optional): データベースファイルパス
    """
    conn = get_connection(db_path)
    if conn is None:
        return

    try:
        cursor = conn.cursor()

        # 全テーブルのデータを削除
        tables = ['daily_records', 'abc_state', 'day_buckets', 'app_settings']
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")

        conn.commit()
        print("全データをクリアしました")

    except Exception as e:
        print(f"データクリアエラー: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    # テスト実行
    print("データベースマネージャーのテスト実行")

    # 接続テスト
    conn = get_connection()
    if conn:
        print("✓ データベース接続成功")
        conn.close()
    else:
        print("✗ データベース接続失敗")