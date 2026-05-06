terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = var.region
}

variable "region" { 
  type = string  
  default = "us-east-1" 
}

variable "name"   { 
  type = string  
  default = "mtc-dev" 
}

variable "anthropic_api_key" { 
  type = string  
  sensitive = true 
}

module "data" {
  source = "../../modules/data"
  name   = var.name
}

module "network" {
  source = "../../modules/network"
  name   = var.name
}

module "compute" {
  source                = "../../modules/compute"
  name                  = var.name
  region                = var.region
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  tool_results_bucket   = module.data.tool_results_bucket_name
  anthropic_api_key     = var.anthropic_api_key
}

module "frontend" {
  source = "../../modules/frontend"
  name   = var.name
  api_domain = module.compute.alb_dns_name
}

output "api_url"      { value = module.compute.alb_dns_name }
output "frontend_url" { value = module.frontend.cloudfront_domain }
output "ecr_repo"     { value = module.compute.ecr_repository_url }
