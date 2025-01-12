# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

class IndentRequest(models.Model):
    _name = 'indent.request'
    _description = 'Indent Request'

    name = fields.Char(strign='Indent No', required=True, index=True, copy=False, default="NEW")
    indent_by = fields.Many2one('res.users', string='Indent By', default=lambda self: self.env.user, readonly=True)
    need_by = fields.Date(string='Need By', required=True)
    indent_date = fields.Date(string='Request Date', default=fields.Date.today, required=True)
    department = fields.Char(string='Department', default=lambda self: self.env.user.department_id.name)
    badge_id = fields.Char(string='Employee ID', readonly=True,
                           default=lambda self: self.env.user.employee_id.barcode
                           if self.env.user.employee_id
                           else 'null')


    item_ids = fields.One2many('indent.request.item', 'indent_id', string='Items')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('refuse', 'Refused'),
        ('close', 'Closed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft')

    def action_submit(self):
        self.state = 'submit'

    def action_approve(self):
        self.state = 'approve'

    def action_refuse(self):
        self.state = 'refuse'

    def action_close(self):
        self.state = 'close'

    def action_cancel(self):
        self.state = 'cancel'

    def action_draft(self):
        self.state = 'draft'

    @api.model
    def create(self, vals):
        if vals.get('name', _('NEW')) == "NEW":
            vals['name'] = self.env['ir.sequence'].next_by_code('indent.request') or "NEW"
        result = super(IndentRequest, self).create(vals)
        logging.info("Created Indent Request with name: %s", result.name)
        return result

class IndentRequestItem(models.Model):
    _name = 'indent.request.item'
    _description = 'Indent Request Item'

    product_id = fields.Many2one('product.template', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    uom = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id', readonly=True, store=True)
    indent_id = fields.Many2one('indent.request', string='Indent Request')