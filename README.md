# manage-mysql-user
AWS Lambda function to manage MySQL users

## Usage
The Lambda accepts the following keys in the payload JSON:   
* `mysql_user_username` - (Required) MySQL username whose password will be updated
* `mysql_user_password_parameter_name` - (Optional, conflicts with `mysql_user_password_secret_name`) Name of SSM parameter that is used to store MySQL user's password
* `mysql_user_password_secret_name` - (Optional, conflicts with `mysql_user_password_parameter_name`) Name of Secrets Manager secret that is used to store MySQL user's password
* `privileges` - (Optional) If present, current privileges will be revoked and then granted as specified here. Accepts a comma-separated list of valid MySQL privileges and optional table names after a colon. See examples below.

###Payload examples
Grants `ALL` on all tables.  
```
{
  "mysql_user_username": "foo",
  "mysql_user_password_secret_name": "bar",
  "privileges": "ALL"
}
```

Grants `SELECT, CREATE, DROP` on all tables: 
```
{
  "mysql_user_username": "foo",
  "mysql_user_password_secret_name": "bar",
  "privileges": "SELECT, CREATE, DROP"
}
```

Grants `SELECT` on all tables, `CREATE` on `table1` and `ALL` on `table2`: 
```
{
  "mysql_user_username": "foo",
  "mysql_user_password_secret_name": "bar",
  "privileges": "SELECT, UPDATE:table1, ALL:table2"
}
```
