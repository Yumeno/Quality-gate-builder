# demo (go-cli example)

Minimal Go CLI used as a qgb example pack.

## Usage

```powershell
go build -o demo.exe ./cmd/demo
.\demo.exe World
```

## Running the quality gate

```powershell
python -m qgb run REQ-APP-001 --path . --yes
```
