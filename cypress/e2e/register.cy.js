describe('Registration flow', () => {
  it('registers a new user with fixed email', () => {
    const email = 'v9957820668@gmail.com'
    const accessKey = '12345678'

    cy.visit('http://127.0.0.1:8000/register/')

    cy.get('input[name="first_name"]').type('Viktor')
    cy.get('input[name="last_name"]').type('Test')
    cy.get('input[name="birth_date"]').type('1995-01-01')
    cy.get('input[name="email"]').type(email)
    cy.get('input[name="phone"]').type('79991234567')
    cy.get('input[name="access_key"]').type(accessKey)
    cy.get('button.register-form__submit').click()

    cy.location('pathname').should('eq', '/register/password/')

    cy.get('input[name="password"]').type('StrongPass123!')
    cy.get('input[name="password_repeat"]').type('StrongPass123!')
    cy.get('button.register-password-form__submit').click()

    cy.location('pathname').should('eq', '/register/success/')
    cy.get('.register-success-card__button').should('be.visible')
  })
})
