<html>
<head>
<title>BackupChecker Report <%=time.strftime('%Y')%>-<%=time.strftime('%m')%>-<%=time.strftime('%d')%></title>
<style>
tr.valid {background-color: #90EE90;}
tr.invalid {background-color: red;}
</style>
</head>
<body>

<script type="text/javascript">
var now = new Date();
var generated_at = new Date(<%=time.strftime('%Y')%>,<%=int(time.strftime('%m'))-1%>,<%=time.strftime('%d')%>,<%=time.strftime('%H')%>,<%=time.strftime('%M')%>);
var diff = now - generated_at;
if ( diff > 1000 * 60 *60 * 24 ) {
    alert("This report is too old! Check backup checker is still running fine!");
}

</script>




<h1>Backup check results <%=time.strftime('%Y')%>-<%=time.strftime('%m')%>-<%=time.strftime('%d')%> <%=time.strftime('%H')%>:<%=time.strftime('%M')%></h1>
<h2>Summary</h2>
<table>
  <tr>
    <th>Backup</th>
    <th>Status</th>
  </tr>
#for $backup in $bc.backups
  <tr class="$backup.status">
    <td>$backup.name</td>
    <td>$backup.status</td>
  </tr>
#end for
</table>

<h2>Detailed Logs</h2>
<pre>
$bc
</pre>
</body>
</html>

