"""BUS XPERIENCE - transcription locale des reponses vocales.

Usage:  pip install faster-whisper
        python transcribe.py
L'audio ne quitte jamais la machine. Detecte FR/DE automatiquement.
"""
import sqlite3
import db

def main():
    from faster_whisper import WhisperModel
    modele = WhisperModel("medium", device="auto", compute_type="int8")
    c = sqlite3.connect(db.DB_PATH); c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT id, audio FROM reponses WHERE audio IS NOT NULL AND transcript IS NULL").fetchall()
    print(f"{len(rows)} reponses a transcrire")
    for r in rows:
        chemin = db.AUDIO / r["audio"]
        if not chemin.exists():
            continue
        segments, info = modele.transcribe(str(chemin), vad_filter=True)
        texte = " ".join(s.text.strip() for s in segments).strip() or "[silence]"
        c.execute("UPDATE reponses SET transcript=? WHERE id=?", (texte, r["id"]))
        c.commit()
        print(f"#{r['id']} ({info.language}) {texte[:70]}")

if __name__ == "__main__":
    main()
