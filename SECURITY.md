# Security reporting and operational guidance

Do not include real plate numbers, MV file numbers, passwords, Fernet keys, setup tokens, or database backups in bug reports.

For a suspected vulnerability, report it privately to the repository owner rather than opening a public issue. Until a contact address is configured, use GitHub's private vulnerability reporting for this repository if available.

Operators should:

- expose the app only through HTTPS;
- restrict SSH and server administration to trusted operators;
- keep `/etc/ncapcheck/ncapcheck.env` and `/var/backups/ncapcheck/` private;
- preserve the Fernet key alongside protected backups, separately and securely;
- patch Ubuntu and Python dependencies regularly;
- use only official authority endpoints and authorized APIs; never bypass CAPTCHA, reCAPTCHA, or access controls.
