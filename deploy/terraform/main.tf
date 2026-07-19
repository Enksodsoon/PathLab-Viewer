resource "oci_core_vcn" "pathlab" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.42.0.0/16"]
  display_name   = "pathlab-viewer"
  dns_label      = "pathlab"
}

resource "oci_core_internet_gateway" "pathlab" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.pathlab.id
  display_name   = "pathlab-public"
  enabled        = true
}

resource "oci_core_route_table" "pathlab" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.pathlab.id
  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.pathlab.id
  }
}

resource "oci_core_security_list" "pathlab" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.pathlab.id
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
  dynamic "ingress_security_rules" {
    for_each = toset(["80", "443"])
    content {
      protocol = "6"
      source   = "0.0.0.0/0"
      tcp_options {
        min = tonumber(ingress_security_rules.value)
        max = tonumber(ingress_security_rules.value)
      }
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = var.admin_cidr
    tcp_options {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_subnet" "pathlab" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.pathlab.id
  cidr_block                 = "10.42.1.0/24"
  display_name               = "pathlab-public"
  dns_label                  = "viewer"
  route_table_id             = oci_core_route_table.pathlab.id
  security_list_ids          = [oci_core_security_list.pathlab.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_instance" "pathlab" {
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "pathlab-viewer"
  shape               = "VM.Standard.A1.Flex"
  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.pathlab.id
    assign_public_ip = true
    display_name     = "pathlab-viewer"
  }
  source_details {
    source_id               = var.image_ocid
    source_type             = "image"
    boot_volume_size_in_gbs = 50
  }
  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }
  lifecycle {
    precondition {
      condition     = var.admin_cidr != "0.0.0.0/0"
      error_message = "SSH must be restricted to a trusted CIDR."
    }
  }
}

resource "oci_core_volume" "data" {
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "pathlab-data"
  size_in_gbs         = 150
  vpus_per_gb         = 10
}

resource "oci_core_volume_attachment" "data" {
  attachment_type                     = "paravirtualized"
  instance_id                         = oci_core_instance.pathlab.id
  volume_id                           = oci_core_volume.data.id
  is_pv_encryption_in_transit_enabled = true
}

resource "oci_budget_budget" "guardrail" {
  compartment_id = var.tenancy_ocid
  amount         = 1
  reset_period   = "MONTHLY"
  target_type    = "COMPARTMENT"
  targets        = [var.compartment_ocid]
  display_name   = "PathLab one-dollar warning"
}

resource "oci_budget_alert_rule" "guardrail" {
  budget_id      = oci_budget_budget.guardrail.id
  threshold      = 100
  threshold_type = "PERCENTAGE"
  type           = "ACTUAL"
  recipients     = var.budget_email
}
