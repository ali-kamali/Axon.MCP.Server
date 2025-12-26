# Axon.Health.HcpCatalogueService.Api

## Overview
- **Type**: API
- **Framework**: net6.0
- **Root Namespace**: `Not specified`
- **Project Path**: `/app/cache/repos/azuredevops/Axon.Health/Axon.Health.HcpCatalog/Axon.Health.HcpCatalogueService.Api/Axon.Health.HcpCatalogueService.Api.csproj`

## Responsibility
**Axon.Health.HcpCatalogueService.Api** is the HTTP‑exposed façade for the Health‑Care‑Provider (HCP) catalogue domain. It provides REST (or gRPC) endpoints that allow other services and client applications to create, read, update, and search the master list of health‑care providers, their specialties, locations, and availability. By centralising this data behind a dedicated API, the service decouples consumer applications from the underlying data store and business logic, ensuring a single source of truth for provider information across the Axon.Health ecosystem.

## Architecture
**Detected Patterns:**
- Dependency Injection
- ASP.NET Core Web API

## API Endpoints
_No API endpoints detected._

## Dependencies
### NuGet Packages
- **K4os.Compression.LZ4** (1.3.6)
- **Elastic.Clients.Elasticsearch** (8.0.4)
- **IdGen** (3.0.1)
- **Microsoft.EntityFrameworkCore** (6.0.11)
- **Microsoft.EntityFrameworkCore.SqlServer** (6.0.11)
- **Microsoft.AspNetCore.Mvc** (2.2.0)
- **Autofac.Extensions.DependencyInjection** (8.0.0)
- **MassTransit** (8.0.6)
- **MassTransit.AspNetCore** (7.3.1)
- **MassTransit.Extensions.DependencyInjection** (7.3.1)
- **MassTransit.RabbitMQ** (8.0.6)
- **Microsoft.Extensions.Caching.StackExchangeRedis** (8.0.0)
- **RestSharp** (108.0.1)
- **RestSharp.Serializers.NewtonsoftJson** (108.0.1)
- **Microsoft.Extensions.Http** (7.0.0)
- **ServiceStack.Redis** (8.0.0)
- **Hangfire.AspNetCore** (1.8.9)
- **Hangfire.Core** (1.8.9)
- **Hangfire.SqlServer** (1.8.9)
- **Microsoft.AspNetCore.Routing** (2.2.2)
- *...and 31 more packages*

### Project References
- Axon.Health.Framework
- Axon.Health.HcpCatalogueService.ApplicationService.Contract
- Axon.Health.HcpCatalogueService.ApplicationService
- Axon.Health.HcpCatalogueService.Domain.Service
- Axon.Health.HcpCatalogueService.Domain
- Axon.Health.HcpCatalogueService.Infrastructure
- Axon.Health.HcpCatalogueService.Retrieval.DataModel
- Axon.Health.HcpCatalogueService.Retrieval

### External Services
_No external service calls detected._

## Events & Messaging
### Publishes
_No events published._

### Subscribes
_No event subscriptions._

## Technical Details
**Service Metadata:**
- Entry Points: 48 controllers
- Detection Reasons: Detected C# Service. Reasons: DI Container Configuration detected, Web SDK detected, Host Builder detected, ASP.NET Core dependency detected, Found 48 Controllers

**File Locations:**
- Project: `/app/cache/repos/azuredevops/Axon.Health/Axon.Health.HcpCatalog/Axon.Health.HcpCatalogueService.Api/Axon.Health.HcpCatalogueService.Api.csproj`
- Documentation: `docs/services/Axon_Health_HcpCatalogueService_Api.md`


---
*Documentation generated on 2025-12-04 14:17:18 UTC*
