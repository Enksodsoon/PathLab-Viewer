variable "region" { type = string }
variable "tenancy_ocid" { type = string }
variable "compartment_ocid" { type = string }
variable "availability_domain" { type = string }
variable "image_ocid" {
  type        = string
  description = "Current Ubuntu aarch64 image OCID verified for VM.Standard.A1.Flex"
}
variable "ssh_public_key" {
  type      = string
  sensitive = true
}
variable "admin_cidr" {
  type        = string
  description = "Single trusted IPv4 CIDR allowed to SSH, restricted to /24 or narrower"
  validation {
    condition = (
      can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$", var.admin_cidr)) &&
      can(cidrnetmask(var.admin_cidr)) &&
      can(tonumber(split("/", var.admin_cidr)[1]) >= 24)
    )
    error_message = "admin_cidr must be a valid IPv4 CIDR with a /24 through /32 prefix."
  }
}
variable "budget_email" { type = string }
