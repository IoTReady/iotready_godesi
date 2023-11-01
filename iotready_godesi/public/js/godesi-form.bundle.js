import Vue from "vue/dist/vue.js";
import ActivityForm from './components/form.vue';


Vue.component('activity-form', ActivityForm);

window.constructFormView = (context) => new Vue({
  el: '#form-root',
  data: {
    session_id: context.session_id,
    activity: context.activity,
    suppliers: context.suppliers || [],
    items: context.items || [],
    target_warehouses: context.target_warehouses || [],
    open_material_requests: context.open_material_requests || [],
    supplier: context.supplier || "",
    item_code: context.item_code || "",
    target_warehouse: context.target_warehouse || "",
    need_label: context.need_label || 0,
    picking_flow: context.picking_flow || "",
    material_request: context.material_request || "",
    parent_crate_id: context.parent_crate_id || "",
    is_manual_picking: context.is_manual_picking || false,
  },
  methods: {
    validate_crate: function(crate) {
      return [true, "", 0]
    },
    update: function(form) {
      if (typeof form === 'string') {
        form = JSON.parse(form);
      }
      if (form.refresh) {
        this.refresh();
      } else if (form.reload) {
        window.location.reload();
      }
    },
    updateVueData: function(key, value) {
      if (key in this.$data) {
        this[key] = value;
      }
    },
    updateMetadata: function(data) {
      // called from child component
      for (let k in data) {
        this.updateVueData(k, data[k]);
      }
    },
    refresh: function() {
      // console.log("Refreshing form");
      frappe.call({
        method: "iotready_godesi.api.get_session_context",
        args: {
          session_id: context.session_id,
        },
        callback: (r) => {
          // console.log(r);
          if (r.message) {
            for (let k in r.message) {
              this.updateVueData(k, r.message[k]);
            }
          }
        }
      });
    },
  },
  mounted() {
  },
})

