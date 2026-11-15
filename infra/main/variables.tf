variable "location" {
  description = "Azure region for all project resources."
  type        = string
  default     = "germanywestcentral"
}

variable "project" {
  description = "Short project name used in resource names."
  type        = string
  default     = "warsaw-transport"
}
