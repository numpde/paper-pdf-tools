# paper-pdf-tools

Place the following scripts in `~/.local/share/nautilus/scripts`.

This script renames a PDF file to the format: YYYY-[Authors] (Paper title).pdf

```bash
#!/bin/bash
LOGFILE=/tmp/paper_filename.log
echo "Running 'paper_filename'" > $LOGFILE
~/repos/paper-pdf-tools/paper_filename.sh "$@" 2>&1 > $LOGFILE
```

This script attempts to remove watermarks (e.g., "Downloaded by Institution such and such").

```bash
#!/bin/bash
LOGFILE=/tmp/remove_watermark.log
echo "Running 'remove_watermark'" > $LOGFILE
~/repos/paper-pdf-tools/remove_watermark.sh "$@" 2>&1 > $LOGFILE
```
