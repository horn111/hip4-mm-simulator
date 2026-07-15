# Grant reviewer demo

Static, evidence-first walkthrough for HIP-4 MM Simulator v0.2. It explains the
causal path from observed L2 through aggressor trade volume, queue consumption,
partial fills, and spot-safe accounting.

The page does not reimplement matching in TypeScript. Its committed replay trace
is exported by the Python engine in the repository root.

## Local development

```bash
python -m pip install -e ..
python ../scripts/export_demo_data.py --check
npm ci
npm run dev
```

## Verification

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

`next build` writes a fully static export to `out/`. On Vercel, set the project
Root Directory to `demo`.
