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
  description = "Single trusted IPv4 CIDR allowed to SSH, never 0.0.0.0/0"
}
variable "budget_email" { type = string }
