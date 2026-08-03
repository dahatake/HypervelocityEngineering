"""ASDW data verifier の静的契約テスト用 fixture。"""
from __future__ import annotations


PRIVATE_VERIFIER = r'''#!/usr/bin/env bash
set -euo pipefail
case "${DATA_NETWORK_MODE:?}" in
  private)
        : "${DATA_VNET_NAME:?}"
        : "${DATA_PRIVATE_ENDPOINT_SUBNET_ID:?}"
        : "${DATA_ACI_SUBNET_ID:?}"
        : "${DATA_NAT_GATEWAY_NAME:?}"
        : "${DATA_DEPLOY_IDENTITY_ID:?}"
        : "${DATA_DEPLOY_IDENTITY_CLIENT_ID:?}"
        : "${SQL_PRIVATE_ENDPOINT_NAME:?}"
        : "${COSMOS_PRIVATE_ENDPOINT_NAME:?}"
        : "${SQL_PRIVATE_DNS_ZONE:?}"
        : "${COSMOS_PRIVATE_DNS_ZONE:?}"
        : "${DATA_VERIFY_ACI_IMAGE:?}"
        : "${DATA_VERIFY_RUN_ID:?}"
                if [[ ! "$DATA_VERIFY_RUN_ID" =~ ^[0-9a-f]{32}$ ]]; then
                    exit 1
                fi
                if ! command -v timeout >/dev/null 2>&1; then
                    exit 1
                fi
                vnet_id="$(az network vnet show --name "$DATA_VNET_NAME" --query id --output tsv)"
                pe_subnet_vnet="$(az network vnet subnet show --ids "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" --query "contains(id, '$vnet_id') && id" --output tsv)"
                aci_subnet_vnet="$(az network vnet subnet show --ids "$DATA_ACI_SUBNET_ID" --query "contains(id, '$vnet_id') && id" --output tsv)"
                if [[ -z "$pe_subnet_vnet" || -z "$aci_subnet_vnet" || "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" == "$DATA_ACI_SUBNET_ID" ]]; then
                    exit 1
                fi
                aci_delegation="$(az network vnet subnet show --ids "$DATA_ACI_SUBNET_ID" --query "delegations[?serviceName=='Microsoft.ContainerInstance/containerGroups'] | length(@)" --output tsv)"
                aci_nat_id="$(az network vnet subnet show --ids "$DATA_ACI_SUBNET_ID" --query "natGateway.id" --output tsv)"
                az network nat gateway show --name "$DATA_NAT_GATEWAY_NAME"
                if [[ "$aci_delegation" != "1" || -z "$aci_nat_id" || "${aci_nat_id##*/}" != "$DATA_NAT_GATEWAY_NAME" ]]; then
                    exit 1
                fi
                sql_pe_state="$(az network private-endpoint show --name "$SQL_PRIVATE_ENDPOINT_NAME" --query "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status" --output tsv)"
                sql_pe_subnet="$(az network private-endpoint show --name "$SQL_PRIVATE_ENDPOINT_NAME" --query "subnet.id" --output tsv)"
                cosmos_pe_state="$(az network private-endpoint show --name "$COSMOS_PRIVATE_ENDPOINT_NAME" --query "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status" --output tsv)"
                cosmos_pe_subnet="$(az network private-endpoint show --name "$COSMOS_PRIVATE_ENDPOINT_NAME" --query "subnet.id" --output tsv)"
                if [[ "$sql_pe_state" != "Approved" || "$cosmos_pe_state" != "Approved" || "$sql_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" || "$cosmos_pe_subnet" != "$DATA_PRIVATE_ENDPOINT_SUBNET_ID" ]]; then
                    exit 1
                fi
                sql_dns_match="$(az network private-endpoint dns-zone-group list --endpoint-name "$SQL_PRIVATE_ENDPOINT_NAME" --query "[?privateDnsZoneConfigs[?contains(privateDnsZoneId, '/privateDnsZones/$SQL_PRIVATE_DNS_ZONE')]] | length(@)" --output tsv)"
                cosmos_dns_match="$(az network private-endpoint dns-zone-group list --endpoint-name "$COSMOS_PRIVATE_ENDPOINT_NAME" --query "[?privateDnsZoneConfigs[?contains(privateDnsZoneId, '/privateDnsZones/$COSMOS_PRIVATE_DNS_ZONE')]] | length(@)" --output tsv)"
                az network private-dns zone show --name "$SQL_PRIVATE_DNS_ZONE"
                az network private-dns zone show --name "$COSMOS_PRIVATE_DNS_ZONE"
                sql_vnet_link_count="$(az network private-dns link vnet list --zone-name "$SQL_PRIVATE_DNS_ZONE" --query "[?contains(virtualNetwork.id, '$vnet_id')] | length(@)" --output tsv)"
                cosmos_vnet_link_count="$(az network private-dns link vnet list --zone-name "$COSMOS_PRIVATE_DNS_ZONE" --query "[?contains(virtualNetwork.id, '$vnet_id')] | length(@)" --output tsv)"
                if [[ "$sql_dns_match" == "0" || "$cosmos_dns_match" == "0" || "$sql_vnet_link_count" == "0" || "$cosmos_vnet_link_count" == "0" ]]; then
                    exit 1
                fi
                identity_client_id="$(az identity show --ids "$DATA_DEPLOY_IDENTITY_ID" --query clientId --output tsv)"
                if [[ -z "$identity_client_id" || "$identity_client_id" != "$DATA_DEPLOY_IDENTITY_CLIENT_ID" ]]; then
                    exit 1
                fi
                aci_command="python -m pip install mssql-python azure-identity azure-cosmos && python -c 'from mssql_python import connect; from azure.identity import DefaultAzureCredential; from azure.cosmos import CosmosClient; import os, sys; client_id=\"$DATA_DEPLOY_IDENTITY_CLIENT_ID\"; sql_connection_string=\"Server=example.database.windows.net;Database=example;UID=$DATA_DEPLOY_IDENTITY_CLIENT_ID;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no\"; connection=connect(sql_connection_string); cursor=connection.cursor(); cursor.execute(\"SELECT COUNT_BIG(*) FROM [dbo].[example]\"); sql_count=cursor.fetchone()[0]; sql_count == 1 or sys.exit(1); credential=DefaultAzureCredential(managed_identity_client_id=client_id); cosmos=CosmosClient(os.environ[\"COSMOS_ENDPOINT\"], credential=credential); container=cosmos.get_database_client(os.environ[\"COSMOS_DATABASE\"]).get_container_client(os.environ[\"COSMOS_CONTAINER\"]); cosmos_count=list(container.query_items(query=\"SELECT VALUE COUNT(1) FROM c\", enable_cross_partition_query=True))[0]; cosmos_count == 1 or sys.exit(1); print(int(sql_count)); print(int(cosmos_count))'"
                aci_created=0
                aci_name="verify-data-$DATA_VERIFY_RUN_ID"
                cleanup_aci() {
                    if [[ "$aci_created" == "1" ]]; then
                        aci_owner="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "tags.hveVerifyRunId" --output tsv 2>/dev/null || true)"
                        if [[ "$aci_owner" == "$DATA_VERIFY_RUN_ID" ]]; then
                            az container delete --resource-group "$RESOURCE_GROUP" --name "$aci_name" --yes || true
                        fi
                    fi
                }
                trap cleanup_aci EXIT INT TERM
                aci_name_count="$(az container list --resource-group "$RESOURCE_GROUP" --query "[?name=='$aci_name'] | length(@)" --output tsv)"
                if [[ "$aci_name_count" != "0" ]]; then
                    exit 1
                fi
            az container create --resource-group "$RESOURCE_GROUP" --name "$aci_name" --image "$DATA_VERIFY_ACI_IMAGE" --subnet "$DATA_ACI_SUBNET_ID" --acr-identity "$DATA_DEPLOY_IDENTITY_ID" --assign-identity "$DATA_DEPLOY_IDENTITY_ID" --restart-policy Never --os-type Linux --cpu 1 --memory 1 --tags hveVerifyRunId="$DATA_VERIFY_RUN_ID" --environment-variables AZURE_CLIENT_ID="$DATA_DEPLOY_IDENTITY_CLIENT_ID" --command-line "$aci_command"
                aci_created=1
                aci_wait_failed=0
                aci_logs="$(timeout 600 az container logs --resource-group "$RESOURCE_GROUP" --name "$aci_name" --follow)" || aci_wait_failed=1
                aci_exit_code="$(az container show --resource-group "$RESOURCE_GROUP" --name "$aci_name" --query "containers[0].instanceView.currentState.exitCode" --output tsv)"
            if [[ "$aci_wait_failed" != "0" || "$aci_exit_code" != "0" || -z "$aci_logs" ]]; then
                exit 1
            fi
    ;;
    public)
        printf '[ERROR] public route evidence schema is undefined\n' >&2
        exit 1
        ;;
    nsp)
        printf '[ERROR] nsp route evidence schema is undefined\n' >&2
        exit 1
        ;;
    blocked)
        printf '[ERROR] blocked route is unresolved\n' >&2
        exit 1
        ;;
    *)
        printf '[ERROR] DATA_NETWORK_MODE is invalid\n' >&2
        exit 1
        ;;
esac
'''
