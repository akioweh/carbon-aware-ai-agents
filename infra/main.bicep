@description('Location for all resources')
param location string = resourceGroup().location

@description('Prefix for resource names')
param prefix string = 'carbon-aware'

@description('Admin username for PostgreSQL')
param pgAdminUser string = 'pgadmin'

@description('Admin password for PostgreSQL')
@secure()
param pgAdminPassword string

@description('The image to use for the scheduler container.')
param schedulerImage string = 'ealen/echo-server:latest'

@description('The image to use for the ui container.')
param uiImage string = 'ealen/echo-server:latest'

@description('The Stats API URL')
param statsApiUrl string = 'http://140.238.79.139:5000'

var sqlContent = loadTextContent('../scheduler/sql/init.sql')

// 1. Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${replace(prefix, '-', '')}registry${uniqueString(resourceGroup().id)}'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// 2. PostgreSQL Flexible Server
resource pgServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: '${prefix}-pgserver-${uniqueString(resourceGroup().id)}'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    version: '15'
    storage: {
      storageSizeGB: 32
    }
  }
}

// Firewall to allow Azure services to connect to PostgreSQL
resource pgFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = {
  parent: pgServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Disable SSL
resource pgConfigSSL 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-03-01-preview' = {
  parent: pgServer
  name: 'require_secure_transport'
  properties: {
    value: 'OFF'
    source: 'user-override'
  }
}

// Create Database
resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: pgServer
  name: 'calendar_db'
}

resource scriptIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-script-id'
  location: location
}

resource scriptStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: take('st${uniqueString(resourceGroup().id)}', 24)
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
}

resource initDbScript 'Microsoft.Resources/deploymentScripts@2020-10-01' = {
  name: '${prefix}-init-db-script'
  location: location
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${scriptIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.50.0'
    storageAccountSettings: {
      storageAccountName: scriptStorage.name
      storageAccountKey: scriptStorage.listKeys().keys[0].value
    }
    environmentVariables: [
      {
        name: 'PGHOST'
        value: pgServer.properties.fullyQualifiedDomainName
      }
      {
        name: 'PGUSER'
        value: pgAdminUser
      }
      {
        name: 'PGPASSWORD'
        secureValue: pgAdminPassword
      }
      {
        name: 'PGDATABASE'
        value: 'calendar_db'
      }
      {
        name: 'SQL_CONTENT'
        value: sqlContent
      }
    ]
    scriptContent: '''
      echo "$SQL_CONTENT" > init.sql
      apk update && apk add postgresql-client
      # psql needs the database to exist. pgDatabase resource handles this.
      psql -h $PGHOST -U $PGUSER -d $PGDATABASE -f init.sql
    '''
    cleanupPreference: 'OnSuccess'
    retentionInterval: 'P1D'
  }
  dependsOn: [
    pgDatabase
    pgConfigSSL
  ]
}

// 3. Container App Environment
resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${prefix}-env'
  location: location
  properties: {
    zoneRedundant: false
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
      {
        name: 'dedicated-d4'
        workloadProfileType: 'D4'
        minimumCount: 1
        maximumCount: 1
      }
    ]
  }
}

// 4. Scheduler Container App (Internal)
resource schedulerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${prefix}-scheduler'
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    workloadProfileName: 'dedicated-d4'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false // Internal only
        targetPort: 6969
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'container-registry-password'
        }
      ]
      secrets: [
        {
          name: 'container-registry-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'pg-password'
          value: pgAdminPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'scheduler'
          image: schedulerImage
          env: [
            { name: 'PORT', value: '6969' }
            { name: 'PGHOST', value: pgServer.properties.fullyQualifiedDomainName }
            { name: 'PGPORT', value: '5432' }
            { name: 'PGDATABASE', value: 'calendar_db' }
            { name: 'PGUSER', value: pgAdminUser }
            { name: 'PGPASSWORD', secretRef: 'pg-password' }
            { name: 'STATS_API_URL', value: statsApiUrl }
          ]
          resources: {
            cpu: json('4')
            memory: '8Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    initDbScript
  ]
}

// 5. UI Container App (Public)
resource uiApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${prefix}-ui'
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true // Public
        targetPort: 3000
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'container-registry-password'
        }
      ]
      secrets: [
        {
          name: 'container-registry-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'ui'
          image: uiImage
          env: [
            { name: 'SCHEDULER_API_URL', value: 'http://${schedulerApp.properties.configuration.ingress.fqdn}' }
            { name: 'STATS_API_URL', value: statsApiUrl }
          ]
          resources: {
            cpu: json('2')
            memory: '4Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output uiUrl string = 'https://${uiApp.properties.configuration.ingress.fqdn}'
