from flask import Flask, render_template, request, redirect, send_from_directory, flash, url_for, abort
from werkzeug.utils import secure_filename
import os
import sqlite3
import time

# --------------------------- FLASK SETUP ---------------------------
app = Flask(__name__)
app.secret_key = "supersecretkey_change_this_in_production"

# Upload folder
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "txt", "ppt", "pptx", "zip", "rar"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = None  # UNLIMITED FILE SIZE

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("database", exist_ok=True)

# --------------------------- DATABASE SETUP ---------------------------
def connect_db():
    conn = sqlite3.connect("database/database.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = connect_db()
    
    # Updated papers table with resource_type
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_name TEXT NOT NULL,
            category TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            year TEXT,
            description TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    conn.close()

create_tables()

# --------------------------- HELPERS ---------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_papers_by_category(category):
    """Get all papers for a specific category"""
    conn = connect_db()
    cur = conn.execute(
        "SELECT * FROM papers WHERE category = ? ORDER BY exam_name, upload_date DESC",
        (category,)
    )
    papers = cur.fetchall()
    conn.close()
    return papers

def get_papers_by_exam(exam_name, category=None):
    """Get all papers for a specific exam"""
    conn = connect_db()
    if category:
        cur = conn.execute(
            "SELECT * FROM papers WHERE exam_name = ? AND category = ? ORDER BY upload_date DESC",
            (exam_name, category)
        )
    else:
        cur = conn.execute(
            "SELECT * FROM papers WHERE exam_name = ? ORDER BY upload_date DESC",
            (exam_name,)
        )
    papers = cur.fetchall()
    conn.close()
    return papers

def get_all_exams_by_category(category):
    """Get unique exam names for a category"""
    conn = connect_db()
    cur = conn.execute(
        "SELECT DISTINCT exam_name FROM papers WHERE category = ? ORDER BY exam_name",
        (category,)
    )
    exams = [row['exam_name'] for row in cur.fetchall()]
    conn.close()
    return exams

def get_paper_count_by_category(category):
    """Count papers in a category"""
    conn = connect_db()
    cur = conn.execute(
        "SELECT COUNT(*) as count FROM papers WHERE category = ?",
        (category,)
    )
    count = cur.fetchone()['count']
    conn.close()
    return count

# --------------------------- ROUTES ---------------------------
@app.route("/")
def home():
    # Get stats for homepage
    conn = connect_db()
    total_papers = conn.execute("SELECT COUNT(*) as count FROM papers").fetchone()['count']
    categories = conn.execute("SELECT DISTINCT category FROM papers").fetchall()
    conn.close()
    
    return render_template("index.html", total_papers=total_papers, total_categories=len(categories))

@app.route("/categories")
def categories():
    """Show all categories with paper counts"""
    categories_list = [
        "UPSC", "NEET", "JEE", "SSC CGL/CHSL", "Banking Exams", 
        "State PSC", "Class 1-12", "University Entrance", "PhD Entrance", "Other"
    ]
    
    category_data = []
    for cat in categories_list:
        count = get_paper_count_by_category(cat)
        category_data.append({"name": cat, "count": count})
    
    return render_template("categories.html", categories=category_data)

@app.route("/category/<category_name>")
def category_view(category_name):
    """View all exams in a specific category"""
    papers = get_papers_by_category(category_name)
    exams = get_all_exams_by_category(category_name)
    
    # Group papers by exam name
    grouped_papers = {}
    for paper in papers:
        exam = paper['exam_name']
        if exam not in grouped_papers:
            grouped_papers[exam] = []
        grouped_papers[exam].append(paper)
    
    return render_template("category_view.html", 
                          category=category_name, 
                          grouped_papers=grouped_papers,
                          exams=exams)

@app.route("/exam/<category_name>/<exam_name>")
def exam_view(category_name, exam_name):
    """View all papers for a specific exam"""
    papers = get_papers_by_exam(exam_name, category_name)
    
    if not papers:
        flash("No papers found for this exam", "error")
        return redirect(f"/category/{category_name}")
    
    return render_template("exam_view.html", 
                          category=category_name,
                          exam_name=exam_name,
                          papers=papers)

@app.route("/papers")
def papers():
    """View all papers with search"""
    search_query = request.args.get("search", "").strip()
    category_filter = request.args.get("category")
    resource_filter = request.args.get("resource_type")
    
    conn = connect_db()
    
    query = "SELECT * FROM papers WHERE 1=1"
    params = []
    
    if search_query:
        query += " AND (exam_name LIKE ? OR category LIKE ? OR description LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
    
    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)
    
    if resource_filter:
        query += " AND resource_type = ?"
        params.append(resource_filter)
    
    query += " ORDER BY upload_date DESC"
    
    cur = conn.execute(query, params)
    papers = cur.fetchall()
    conn.close()
    
    return render_template("papers.html", papers=papers, search_query=search_query)

@app.route("/resources")
def resources():
    """Show all resources (question papers, books, notes, etc.)"""
    resource_type = request.args.get("type", "all")
    
    conn = connect_db()
    
    if resource_type == "all":
        cur = conn.execute("SELECT * FROM papers ORDER BY resource_type, upload_date DESC")
    else:
        cur = conn.execute(
            "SELECT * FROM papers WHERE resource_type = ? ORDER BY upload_date DESC",
            (resource_type,)
        )
    
    resources = cur.fetchall()
    
    # Get counts by type
    resource_counts = {}
    count_cur = conn.execute("SELECT resource_type, COUNT(*) as count FROM papers GROUP BY resource_type")
    for row in count_cur.fetchall():
        resource_counts[row['resource_type']] = row['count']
    
    conn.close()
    
    return render_template("resources.html", 
                          resources=resources, 
                          resource_type=resource_type,
                          resource_counts=resource_counts)

@app.route("/paper/<int:paper_id>")
def view_paper(paper_id):
    """View individual paper with preview"""
    conn = connect_db()
    cur = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    paper = cur.fetchone()
    conn.close()
    
    if not paper:
        flash("Paper not found", "error")
        return redirect("/papers")
    
    # Get related papers (same exam)
    related_papers = get_papers_by_exam(paper['exam_name'], paper['category'])
    related_papers = [p for p in related_papers if p['id'] != paper_id][:5]
    
    return render_template("view_paper.html", paper=paper, related_papers=related_papers)

@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    if request.method == "POST":
        exam_name = request.form.get("exam_name", "").strip()
        category = request.form.get("category", "").strip()
        resource_type = request.form.get("resource_type", "").strip()
        year = request.form.get("year", "").strip()
        description = request.form.get("description", "").strip()
        file = request.files.get("file")

        # Validation
        if not exam_name or not category or not resource_type:
            flash("Please fill in all required fields", "error")
            return redirect(request.url)

        if not file or file.filename == "":
            flash("No file selected", "error")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file type. Allowed: PDF, DOC, DOCX, PPT, PPTX, JPG, PNG, ZIP, RAR, TXT", "error")
            return redirect(request.url)

        try:
            filename = secure_filename(file.filename)
            base, ext = os.path.splitext(filename)
            filename = f"{base}_{int(time.time())}{ext}"
            
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)

            conn = connect_db()
            conn.execute(
                """INSERT INTO papers (exam_name, category, resource_type, filename, filepath, year, description) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (exam_name, category, resource_type, filename, save_path, year, description)
            )
            conn.commit()
            conn.close()

            flash(f"Upload successful! Your {resource_type} has been added.", "success")
            return redirect(f"/category/{category}")

        except Exception as e:
            flash(f"Upload failed: {str(e)}", "error")
            return redirect(request.url)

    return render_template("upload.html")

@app.route("/view/<filename>")
def view_file(filename):
    """View file in browser"""
    try:
        ext = filename.rsplit(".", 1)[1].lower()
        
        if ext == "pdf":
            return send_from_directory(app.config["UPLOAD_FOLDER"], filename, mimetype='application/pdf')
        elif ext in ["jpg", "jpeg", "png", "gif"]:
            return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
        elif ext == "txt":
            return send_from_directory(app.config["UPLOAD_FOLDER"], filename, mimetype='text/plain')
        else:
            flash("This file type cannot be previewed. Downloading instead.", "error")
            return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)
    except Exception as e:
        flash(f"File not found: {str(e)}", "error")
        return redirect("/papers")

@app.route("/download/<filename>")
def download(filename):
    """Download file"""
    try:
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)
    except Exception as e:
        flash(f"File not found: {str(e)}", "error")
        return redirect("/papers")

@app.route("/sitemap.xml")
def sitemap():
    """Generate sitemap for SEO"""
    conn = connect_db()
    cur = conn.execute("SELECT id, exam_name, category, upload_date FROM papers ORDER BY id DESC")
    papers = cur.fetchall()
    conn.close()
    
    return render_template("sitemap.xml", papers=papers), 200, {'Content-Type': 'application/xml'}

@app.route("/robots.txt")
def robots():
    """Robots.txt for search engines"""
    return """User-agent: *
Allow: /
Sitemap: https://yourdomain.com/sitemap.xml""", 200, {'Content-Type': 'text/plain'}

# --------------------------- ERROR HANDLERS ---------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html") if os.path.exists("templates/404.html") else ("Page not found", 404)

@app.errorhandler(413)
def too_large(e):
    flash("File upload failed. Please try again.", "error")
    return redirect("/upload")

# --------------------------- RUN SERVER ---------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)