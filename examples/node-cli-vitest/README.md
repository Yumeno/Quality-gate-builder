# demo-cli (node-cli-vitest example)

Minimal Node.js CLI used as a qgb example pack.

## Requirements

- Node.js 22.23.4 or later (declared in `package.json` `engines.node`).
  `.npmrc` sets `engine-strict=true`, so `npm install` fails on older Node.js.

## Usage

```powershell
npm install
node src/index.js World
```

## Running the quality gate

```powershell
python -m qgb run REQ-APP-001 --path . --yes
```
