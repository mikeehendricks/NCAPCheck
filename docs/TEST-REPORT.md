# NCAPCheck test report

**Release under test:** `0.1.0`  
**Test date:** 2026-10-19  
**Environment:** Python 3.13 sandbox, Flask test client, headless Chromium, SQLite test databases

## Results

| Check | Result |
|---|---|
| `pytest -q` | **20 passed** |
| `ruff check .` | **Passed** |
| `bash -n scripts/install-ubuntu.sh scripts/update-server.sh scripts/backup.sh` | **Passed** |
| Browser sign-in and dashboard | **Passed** |
| Add vehicle and save a manual observation | **Passed** |
| Admin one-time bootstrap and aggregate admin panel | **Passed** |
| Responsive viewport at 390 px | **Passed; no horizontal overflow** |
| Ubuntu server installation | **Not run on an Ubuntu host**; see limitation below |

## Coverage / usability checks

- User registration, sign-in/sign-out, password checks, one-time admin token, and second-use rejection.
- Access control between users; standard users cannot open the admin panel; admin aggregate view does not reveal plate/MV values.
- Vehicle validation, encryption-at-rest for plate/MV and manual notes, manual result history, vehicle deletion, and consolidated manual-report state.
- Scheduler interval and due-task behavior; a due vehicle creates one manual-review task per configured portal, advances its next due date, and does not submit identifiers to an authority website.
- Administrator interval bounds, registration policy toggle, GitHub release metadata handling, controlled update command, and CSRF rejection.
- Browser flow: sign in → add sample vehicle → open details → record a manual observation. The admin flow was separately exercised with the bootstrap token.
- Screenshots in this directory were captured from the local app using sample values only.

## Defect found during testing

The first test pass exposed error handlers rendering 403/404 templates without Flask's normal request/template context. The handlers were corrected to use `render_template`; regression tests now cover both cases. The final suite passes.

## Known integration blocker

The listed authority sites currently require interactive browser verification, return reCAPTCHA/Cloudflare challenge content, or deny automated access from the development network. No authorized API credentials or endpoints were provided. Therefore, automated violation-status retrieval was not implemented; scheduled tasks are reminders, and user-entered observations are visibly not authority-verified. Do not treat them as legal or official records.

## Deployment limitation

The build sandbox is Debian, and no Ubuntu server credentials or target hostname were provided. The installer passed shell syntax checks but was **not** executed end-to-end on Ubuntu. Validate it on a clean Ubuntu 22.04+ VM, confirm DNS/TLS and systemd behavior, then deploy to production.
