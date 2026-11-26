from backend import create_app

app = create_app()

if __name__ == "__main__":
    print("=" * 60)
    print("  PostMini API Client running at http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=True)
