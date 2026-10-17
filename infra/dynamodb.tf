resource "aws_dynamodb_table" "herd" {
  name         = "ranchhand-herd"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "pk"
  range_key = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "number"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "date_of_birth"
    type = "S"
  }

  attribute {
    name = "sire_id"
    type = "S"
  }

  attribute {
    name = "dam_id"
    type = "S"
  }

  global_secondary_index {
    name = "number-index"
    key_schema {
      attribute_name = "number"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "pk"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  global_secondary_index {
    name = "status-index"
    key_schema {
      attribute_name = "status"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "date_of_birth"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  global_secondary_index {
    name = "sire-index"
    key_schema {
      attribute_name = "sire_id"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "date_of_birth"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  global_secondary_index {
    name = "dam-index"
    key_schema {
      attribute_name = "dam_id"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "date_of_birth"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled = true
  }
}
