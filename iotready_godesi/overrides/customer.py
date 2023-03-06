from erpnext.selling.doctype.customer.customer import Customer

class CustomCustomer(Customer):
    def autoname(self):
        print("inside customer_autoname", self)
        