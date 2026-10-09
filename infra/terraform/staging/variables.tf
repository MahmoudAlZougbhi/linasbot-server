variable "region" {
  type    = string
  default = "lon1"
}

variable "kubernetes_version" {
  type    = string
  default = "1.34.12-do.0"
}

variable "spaces_access_key_id" {
  type    = string
  default = ""
}

variable "spaces_secret_access_key" {
  type      = string
  default   = ""
  sensitive = true
}
