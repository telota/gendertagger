"""
Database management for the gender annotation application.
"""
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List
import pandas as pd
from datetime import datetime


class Database:
    """SQLite database manager for gender annotations."""
    
    def __init__(self, db_path: Path):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.setup_tables()
    
    def setup_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Persons table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS persons (
                xml_id TEXT PRIMARY KEY,
                name TEXT,
                forename TEXT,
                surname TEXT,
                sex TEXT,
                birth_date TEXT,
                death_date TEXT,
                notes TEXT,
                gnd_id TEXT,
                source_file TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Annotations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_xml_id TEXT NOT NULL,
                human_gender TEXT NOT NULL,
                annotator_name TEXT,
                is_uncertain BOOLEAN DEFAULT 0,
                annotation_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_xml_id) REFERENCES persons(xml_id)
            )
        """)
        
        # Classifier results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classifier_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_xml_id TEXT NOT NULL,
                classifier_name TEXT NOT NULL,
                predicted_gender TEXT NOT NULL,
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_xml_id) REFERENCES persons(xml_id),
                UNIQUE(person_xml_id, classifier_name)
            )
        """)
        
        # Leaderboard table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                score INTEGER NOT NULL,
                time_seconds REAL NOT NULL,
                questions_answered INTEGER NOT NULL,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    def import_persons(self, df: pd.DataFrame):
        """
        Import persons from a DataFrame.
        
        Args:
            df: DataFrame with person data
        """
        # Ensure required columns exist
        required_cols = ['xml_id', 'name', 'forename', 'surname']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Optional columns with defaults
        optional_cols = {
            'sex': '',
            'birth_date': '',
            'death_date': '',
            'notes': '',
            'gnd_id': '',
            'source_file': ''
        }
        
        for col, default in optional_cols.items():
            if col not in df.columns:
                df[col] = default
        
        # Insert or replace persons
        df.to_sql('persons', self.conn, if_exists='replace', index=False)
        self.conn.commit()
    
    def get_persons_with_annotations(self) -> pd.DataFrame:
        """
        Get all persons with their annotations.
        
        Returns:
            DataFrame with persons and annotation data
        """
        query = """
            SELECT 
                p.*,
                a.human_gender,
                a.annotator_name,
                a.is_uncertain,
                a.annotation_time,
                a.updated_at as annotation_date
            FROM persons p
            LEFT JOIN (
                SELECT person_xml_id, human_gender, annotator_name, 
                       is_uncertain, annotation_time, updated_at,
                       ROW_NUMBER() OVER (PARTITION BY person_xml_id ORDER BY updated_at DESC) as rn
                FROM annotations
            ) a ON p.xml_id = a.person_xml_id AND a.rn = 1
            ORDER BY p.surname, p.forename
        """
        
        return pd.read_sql_query(query, self.conn)
    
    def save_annotation(
        self,
        person_xml_id: str,
        gender: str,
        annotator: str,
        is_uncertain: bool = False,
        annotation_time: Optional[float] = None
    ):
        """
        Save or update an annotation.
        
        Args:
            person_xml_id: XML ID of the person
            gender: Annotated gender ('male', 'female', 'unknown', 'institution')
            annotator: Name of the annotator
            is_uncertain: Whether the annotation is uncertain
            annotation_time: Time taken for annotation (seconds)
        """
        cursor = self.conn.cursor()
        
        # Check if annotation exists
        cursor.execute(
            "SELECT id FROM annotations WHERE person_xml_id = ? ORDER BY created_at DESC LIMIT 1",
            (person_xml_id,)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            cursor.execute("""
                UPDATE annotations 
                SET human_gender = ?, annotator_name = ?, is_uncertain = ?,
                    annotation_time = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (gender, annotator, is_uncertain, annotation_time, existing[0]))
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO annotations 
                (person_xml_id, human_gender, annotator_name, is_uncertain, annotation_time)
                VALUES (?, ?, ?, ?, ?)
            """, (person_xml_id, gender, annotator, is_uncertain, annotation_time))
        
        self.conn.commit()
    
    def delete_annotation(self, person_xml_id: str):
        """
        Delete annotations for a person.
        
        Args:
            person_xml_id: XML ID of the person
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM annotations WHERE person_xml_id = ?", (person_xml_id,))
        self.conn.commit()
    
    def get_annotation_statistics(self) -> Dict:
        """
        Get annotation statistics.
        
        Returns:
            Dictionary with statistics
        """
        cursor = self.conn.cursor()
        
        # Total persons
        cursor.execute("SELECT COUNT(*) FROM persons")
        total_persons = cursor.fetchone()[0]
        
        # Annotated count
        cursor.execute("""
            SELECT COUNT(DISTINCT person_xml_id) 
            FROM annotations 
            WHERE human_gender IS NOT NULL
        """)
        annotated_count = cursor.fetchone()[0]
        
        # Uncertain count
        cursor.execute("""
            SELECT COUNT(DISTINCT person_xml_id) 
            FROM annotations 
            WHERE is_uncertain = 1
        """)
        uncertain_count = cursor.fetchone()[0]
        
        # Gender distribution
        cursor.execute("""
            SELECT human_gender, COUNT(*) as count
            FROM (
                SELECT person_xml_id, human_gender,
                       ROW_NUMBER() OVER (PARTITION BY person_xml_id ORDER BY updated_at DESC) as rn
                FROM annotations
            )
            WHERE rn = 1
            GROUP BY human_gender
        """)
        gender_dist = dict(cursor.fetchall())
        
        return {
            'total_persons': total_persons,
            'annotated_count': annotated_count,
            'uncertain_count': uncertain_count,
            'gender_distribution': gender_dist
        }
    
    def save_classifier_result(
        self,
        person_xml_id: str,
        classifier_name: str,
        predicted_gender: str,
        confidence: float
    ):
        """
        Save classifier prediction result.
        
        Args:
            person_xml_id: XML ID of the person
            classifier_name: Name of the classifier
            predicted_gender: Predicted gender
            confidence: Confidence score (0-1)
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO classifier_results
            (person_xml_id, classifier_name, predicted_gender, confidence, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (person_xml_id, classifier_name, predicted_gender, confidence))
        
        self.conn.commit()
    
    def get_classifier_results(self, person_xml_id: str) -> pd.DataFrame:
        """
        Get classifier results for a person.
        
        Args:
            person_xml_id: XML ID of the person
            
        Returns:
            DataFrame with classifier results
        """
        query = """
            SELECT classifier_name, predicted_gender, confidence
            FROM classifier_results
            WHERE person_xml_id = ?
            ORDER BY confidence DESC
        """
        
        return pd.read_sql_query(query, self.conn, params=(person_xml_id,))
    
    def add_leaderboard_entry(
        self,
        player_name: str,
        score: int,
        time_seconds: float,
        questions_answered: int
    ):
        """
        Add an entry to the leaderboard.
        
        Args:
            player_name: Name of the player
            score: Final score
            time_seconds: Time taken (seconds)
            questions_answered: Number of questions answered
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO leaderboard
            (player_name, score, time_seconds, questions_answered)
            VALUES (?, ?, ?, ?)
        """, (player_name, score, time_seconds, questions_answered))
        
        self.conn.commit()
    
    def get_leaderboard(self, limit: int = 10) -> pd.DataFrame:
        """
        Get leaderboard entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            DataFrame with leaderboard entries
        """
        query = """
            SELECT 
                ROW_NUMBER() OVER (ORDER BY score DESC, time_seconds ASC) as rank,
                player_name,
                score,
                time_seconds,
                questions_answered,
                played_at
            FROM leaderboard
            ORDER BY score DESC, time_seconds ASC
            LIMIT ?
        """
        
        return pd.read_sql_query(query, self.conn, params=(limit,))
    
    def close(self):
        """Close database connection."""
        self.conn.close()


def init_database(db_path: Optional[Path] = None) -> Database:
    """
    Initialize the database.
    
    Args:
        db_path: Path to database file (defaults to data/annotations.db)
        
    Returns:
        Database instance
    """
    if db_path is None:
        # Default to data directory in project root
        project_root = Path(__file__).parent.parent.parent.parent
        db_path = project_root / "data" / "annotations.db"
    
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    return Database(db_path)
