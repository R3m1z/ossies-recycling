def employee_login():
    if request.method == "POST":
        name = request.form.get("employee_name", "").strip()
        if not name:
            flash("Enter your name to continue", "danger")
            return redirect(url_for("employee_login"))
        session["employee_name"] = name
        return redirect(url_for("employee_payout"))
    return render_template("employee_login.html")
