# Pharmacy Management System

A fully offline desktop application for managing a medical pharmacy: inventory,
billing/POS, customers, suppliers, users, reports, and backup/restore.

## Tech stack

- **Python 3** + **PySide6** (Qt6 GUI bindings)
- **SQLite** (local file, auto-created on first run — see "Where data lives" below)
- **reportlab** for PDF invoices/reports, **openpyxl** for Excel exports
- **PyInstaller** for packaging into a single Windows `.exe`

No internet connection is required for any feature.

## Project structure

```
pharmacy-app/
  main.py                 Entry point
  requirements.txt
  pharmacy_app.spec       PyInstaller build spec
  installer.iss           Inno Setup script (builds the deployable installer)
  database/
    schema.sql            Table definitions
    db_manager.py          Connection handling, schema init, default admin seed
  logic/                   Business logic (one module per feature area)
    security.py            Password hashing (PBKDF2)
    auth.py                 Login + user management
    inventory.py            Medicine CRUD, stock, low-stock/expiry alerts
    suppliers.py             Supplier CRUD + purchase orders (stock intake)
    customers.py             Customer CRUD + sales history
    sales.py                  Cart + checkout (POS)
    invoice_pdf.py             Printable invoice PDF generation
    reports.py                  Daily/monthly/profit-loss/expiry reports
    report_export.py             Excel/PDF export helpers
    backup.py                     Backup/restore/auto-backup/retention
    settings.py                    Configurable thresholds
  ui/                      PyQt/PySide6 forms (one view per feature area)
  data/                    pharmacy.db lives here (auto-created)
  backups/                 Backup files land here by default
  invoices/                Generated invoice PDFs
```

## Running the app (development)

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python main.py
```

On first run, the database and all tables are created automatically, along
with a default administrator account:

- **Username:** `admin`
- **Password:** `admin123`

**Change this password immediately** after first login (Settings → User
Management → Edit → set a new password).

## Roles

- **Admin**: full access to every module, including Inventory add/edit/delete,
  Suppliers, Backup/Restore, Settings, and User Management.
- **Cashier**: Billing (POS) and read-only Inventory/Customers/Reports. No
  edit/delete rights.

## Barcode scanning (Billing)

A USB/Bluetooth barcode scanner is just a keyboard emulator — it "types" the
barcode digits into whatever text field has focus and then sends an Enter
key press. The Billing screen's search box is built for exactly this: click
into it once, then scan — each scan looks up the barcode, adds one unit to
the cart (scanning the same item again just increases its quantity), and
clears the box so it's ready for the next scan. Stock is only deducted from
Inventory when the sale is actually checked out, not while items sit in the
cart.

Barcodes are optional per medicine (set in Inventory → Add/Edit Medicine →
Barcode field) — a medicine without one can still be sold by typing its name.

**Generating your own barcodes**: many medicines (loose/repackaged stock,
locally made items) don't come with a manufacturer barcode. In the
Add/Edit Medicine dialog, click **🏷️ Generate** to create a unique internal
code (`PHxxxxxxxx`), then **🖨️ Print Label** to produce a small printable
PDF (name + price + barcode) saved to the `labels/` folder — print it,
stick it on the product, and it scans in Billing exactly like any other
barcode (Code128 encodes plain text, so there's no manufacturer-specific
format requirement).

## Backup & Restore

- **Backup Now** (Dashboard or Backup/Restore page): one click, saves a
  timestamped copy of the database to `backups/` (or a custom folder you pick,
  e.g. a USB drive).
- **Restore Backup**: pick a `.db` file, confirm the warning, and the app
  restarts automatically with the restored data. A safety copy of the
  pre-restore database is kept in `data/` just in case.
- **Backup History**: view and delete past backups from inside the app.
- **Auto-backup**: runs silently once per day on first login, and again
  whenever the app is closed. Only the last 15 auto-backups are kept
  (manual backups are never auto-deleted).

## Packaging into a single .exe

```bash
pip install pyinstaller
pyinstaller pharmacy_app.spec
```

The finished executable is written to `dist/PharmacyManagementSystem.exe`.

**Where data lives when packaged:** the frozen .exe stores its database,
backups, and invoices under `%LOCALAPPDATA%\PharmacyManagementSystem\`
(e.g. `C:\Users\<user>\AppData\Local\PharmacyManagementSystem\data\pharmacy.db`)
— **not** next to the .exe itself. This is deliberate: the installer places
the executable in `C:\Program Files\...`, and a normal (non-admin) running
process cannot write there, so app data must live in a per-user writable
folder regardless of where the .exe is installed. In development (running
via `python main.py`, not frozen), data still lives in the project's own
`data/`/`backups/`/`invoices/` folders for convenience.

Re-run `pyinstaller pharmacy_app.spec` any time after changing the source to
rebuild.

## Building the Windows installer (for deploying to shop PCs)

The raw `.exe` above can be run directly, but for deploying to many
different shop PCs, build a proper installer with **Inno Setup**
(`installer.iss`) — it adds a Start Menu entry (so the app is searchable via
Windows Search), an optional Desktop shortcut, and a proper uninstaller
listed in "Add or Remove Programs":

```bash
winget install --id JRSoftware.InnoSetup -e   # one-time, if not installed
"C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

This produces `installer_output\PharmacyManagementSystem_Setup.exe` — copy
just this one file to each shop's PC and run it. It installs to
`C:\Program Files\PharmacyManagementSystem` (a one-time admin/UAC prompt is
normal and expected) and each shop's own data ends up in that PC's own
`%LOCALAPPDATA%\PharmacyManagementSystem\`, completely independent of other
shops' data.

Rebuild both the `.exe` and the installer together after any source change —
the installer script always bundles whatever is currently in `dist/`.

## Notes / known simplifications

- The `medicines` table (per the required schema) holds one batch/expiry per
  medicine row rather than per-batch lots; receiving new stock via a Purchase
  Order updates the batch/expiry/quantity on that same row.
- Profit/loss reporting uses each medicine's *current* purchase price (the
  schema does not store a historical cost price per sale).
