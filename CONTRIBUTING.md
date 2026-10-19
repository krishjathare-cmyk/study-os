# Contributing to Study OS

Follow the setup steps in [the README](readme.md). Use Node.js 22 and Python
3.12 to match the container and CI environments. Install backend dependencies
from `backend/requirements.txt`; the root requirements file is a legacy snapshot.

Before opening a pull request, run:

```bash
cd frontend
npm ci
npm run build
cd ../backend
python -m unittest discover -s tests
```

Keep changes focused. Describe the problem, resulting behavior, and checks run.
For UI changes, include screenshots using synthetic study content. Add regression
coverage when changing authentication, billing, upload processing, or study logic.

Never commit environment files, tokens, real student documents, database files,
recordings, downloaded models, or build output. Keep public configuration examples
in sync with new settings. Report suspected security issues privately to the
repository owner; do not put credentials or exploit details in public issues.

The repository currently has no license grant. The owner should choose a license
before inviting redistribution or reuse.
