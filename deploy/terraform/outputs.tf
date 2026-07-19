output "public_ip" { value = oci_core_instance.pathlab.public_ip }
output "instance_id" { value = oci_core_instance.pathlab.id }
output "data_volume_id" { value = oci_core_volume.data.id }
