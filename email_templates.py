def _base_template(content: str) -> str:
    """Wrap email content in a consistent branded layout."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f7;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="background-color:#2563eb;padding:24px 32px;">
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;">CE Logbook</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              {content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#f9fafb;border-top:1px solid #e5e7eb;">
              <p style="margin:0;font-size:12px;color:#6b7280;text-align:center;">
                CE Logbook &mdash; Free Continuing Education tracking for financial professionals.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta_button(url: str, label: str) -> str:
    """Generate an inline-styled CTA button."""
    return (
        f'<a href="{url}" style="display:inline-block;padding:12px 28px;'
        f'background-color:#2563eb;color:#ffffff;text-decoration:none;'
        f'border-radius:6px;font-size:16px;font-weight:600;">{label}</a>'
    )


def password_reset_email(username: str, reset_url: str) -> str:
    """HTML email for password reset."""
    content = f"""
<h2 style="margin:0 0 16px;color:#111827;font-size:20px;">Reset Your Password</h2>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Hi {username},
</p>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  We received a request to reset your password. Click the button below to choose a new one.
  This link will expire in 1 hour.
</p>
<p style="margin:28px 0;text-align:center;">
  {_cta_button(reset_url, "Reset Password")}
</p>
<p style="color:#6b7280;font-size:13px;line-height:1.5;">
  If you didn't request this, you can safely ignore this email. Your password will remain unchanged.
</p>"""
    return _base_template(content)


def welcome_email(username: str, login_url: str) -> str:
    """HTML email for new user welcome."""
    content = f"""
<h2 style="margin:0 0 16px;color:#111827;font-size:20px;">Welcome to CE Logbook!</h2>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Hi {username},
</p>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Your account has been created successfully. You can now start tracking your
  Continuing Education credits across all your designations.
</p>
<p style="margin:28px 0;text-align:center;">
  {_cta_button(login_url, "Log In to CE Logbook")}
</p>
<p style="color:#6b7280;font-size:13px;line-height:1.5;">
  If you didn't create this account, please disregard this email.
</p>"""
    return _base_template(content)


def deadline_reminder_email(username: str, designation: str, hours_remaining: float, deadline_date: str) -> str:
    """HTML email for CE deadline reminder."""
    content = f"""
<h2 style="margin:0 0 16px;color:#111827;font-size:20px;">CE Deadline Reminder</h2>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Hi {username},
</p>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Your <strong>{designation}</strong> reporting period ends on <strong>{deadline_date}</strong>.
  You still need <strong>{hours_remaining} hours</strong> to meet your requirement.
</p>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Log in to review your progress and add any recent CE credits.
</p>
<p style="margin:28px 0;text-align:center;">
  {_cta_button("#", "View Dashboard")}
</p>
<p style="color:#6b7280;font-size:13px;line-height:1.5;">
  This is an automated reminder from CE Logbook.
</p>"""
    return _base_template(content)


def pending_record_email(username: str, course_title: str) -> str:
    """HTML email notifying user that a new CE record was extracted from a forwarded email."""
    content = f"""
<h2 style="margin:0 0 16px;color:#111827;font-size:20px;">New CE Record Ready for Review</h2>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Hi {username},
</p>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  We received a forwarded email and extracted a CE record for you:
</p>
<p style="color:#111827;font-size:16px;font-weight:600;background-color:#f3f4f6;padding:12px 16px;border-radius:6px;border-left:4px solid #2563eb;">
  {course_title}
</p>
<p style="color:#374151;font-size:15px;line-height:1.6;">
  Please review the extracted details and approve or reject the record.
</p>
<p style="margin:28px 0;text-align:center;">
  {_cta_button("#", "Review Pending Records")}
</p>
<p style="color:#6b7280;font-size:13px;line-height:1.5;">
  This is an automated notification from CE Logbook.
</p>"""
    return _base_template(content)
