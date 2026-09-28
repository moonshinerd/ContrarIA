lines = open("app/jobs/refresh_engagement.py").read().split("\n")
for i in range(66, 134):
    if lines[i].startswith("                    "):
        lines[i] = "            " + lines[i][20:]
    elif lines[i].startswith("                "):
        lines[i] = "            " + lines[i][16:]
open("app/jobs/refresh_engagement.py", "w").write("\n".join(lines))
