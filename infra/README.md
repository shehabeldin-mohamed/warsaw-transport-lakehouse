# Infrastructure

Terraform for the Azure side of the project. Two stacks:

| Stack | Creates | Keeps its state in |
|---|---|---|
| `bootstrap/` | `rg-warsaw-transport-tfstate` with a storage account and a `tfstate` container (the remote state backend) | a local `terraform.tfstate`, not in git |
| `main/` | `rg-warsaw-transport` and everything in it | `tfstate/warsaw.tfstate` in the bootstrap storage account |

Bootstrap is applied once and never destroyed. Main can be destroyed and rebuilt at any time.

## Prerequisites

- Terraform >= 1.9 and the Azure CLI
- `az login`, with the target subscription selected
- The subscription id in the environment (the azurerm provider needs it; it is not stored in the repo):

```powershell
$env:ARM_SUBSCRIPTION_ID = az account show --query id -o tsv
```

## First-time setup (already done for this project)

```powershell
cd infra/bootstrap
terraform init
terraform apply
terraform output -raw backend_config | Set-Content -Encoding ascii ../main/backend.hcl   # then commit it
```

The storage account has shared keys disabled, so access is through Entra ID only. The bootstrap gives the person running it the Storage Blob Data Contributor role on it.

## Everyday use

```powershell
cd infra/main
terraform init "-backend-config=backend.hcl"   # once per machine; quotes needed in PowerShell
terraform plan
terraform apply
```
