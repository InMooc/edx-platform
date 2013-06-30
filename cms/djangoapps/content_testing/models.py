from django.db import models
from xmodule.modulestore.django import modulestore
from xmodule.modulestore import Location
from contentstore.views.preview import get_preview_module
import pickle


class ContentTest(models.Model):
    '''model for a test of a custom response problem'''

    # the problem to test (location)
    # future-proof against long locations?
    problem_location = models.CharField(max_length=100, editable=False)

    # whether the problem should evaluate as correct or not
    # TODO: make this a dict of correctness for each input
    should_be = models.BooleanField()

    # the current state of the test
    verdict = models.NullBooleanField(editable=False)

    # pickle of dictionary that is the stored input
    response_dict = models.TextField(blank=True)

    def __init__(self, *arg, **kwargs):
        '''pickle the dictionary for storage, and stringify the location'''

        if 'response_dict' not in kwargs:
            kwargs['response_dict'] = {}

        kwargs['response_dict'] = pickle.dumps(kwargs['response_dict'])
        kwargs['problem_location'] = str(kwargs['problem_location'])
        super(ContentTest, self).__init__(*arg, **kwargs)

        print self.pk

    def _make_capa(self):
        # create a preview capa problem
        # try:
        problem_descriptor = modulestore().get_item(Location(self.problem_location))
        # except:
        #     raise LookupError

        problem_module = get_preview_module(0, problem_descriptor)
        problem_capa = problem_module.lcp

        return problem_capa

    def run(self):
        '''run the test, and see if it passes'''

        # process dictionary that is the response from grading
        grade_dict = self.evaluate(self._create_response_dictionary())

        # compare the result with what is should be
        self.verdict = self.make_verdict(grade_dict)

        # write the change to the database and return the result
        self.save()
        return self.verdict

    def evaluate(self, response_dict):
        '''evaluate the problem with the response_dict and return the correct/incorrect result'''

        # instantiate the capa problem so it can grade itself
        capa = self._make_capa()
        grade_dict = capa.grade_answers(response_dict)
        return grade_dict

    def make_verdict(self, correct_map):
        '''compare what the result of the grading should be with the actual grading'''

        # this will all change because self.shuold_be will become a dictionary!!
        passing_all = True
        for grade in correct_map.get_dict().values():
            if grade['correctness'] == 'incorrect':
                passing_all = False
                break

        if self.should_be:
            return passing_all
        else:
            return not(passing_all)

    def _create_response_dictionary(self):
        '''create dictionary to be submitted to the grading function'''
        # why not just store this dictionary directly in the database??
        # as a string and reconstruct here?

        response_dict = {}
        for resp_model in self.response_set.all():
            for input_model in resp_model.input_set.all():
                response_dict[input_model.string_id] = input_model.answer

        return response_dict

    def _create_children(self):
        '''create child responses and input entries when created'''

        # create a preview capa problem
        problem_capa = self._make_capa()

        # go through responder objects
        for responder_xml, responder in problem_capa.responders.iteritems():

            # put the response object in the database
            response_model = Response.objects.create(
                content_test=self,
                xml=responder_xml,
                string_id=responder.id)

            # tell it to put its children in the database
            response_model._create_children(responder, pickle.loads(self.response_dict))


class Response(models.Model):
    '''Object that corresponds to the <_____response> fields'''

    # the tests in which this response resides
    content_test = models.ForeignKey(ContentTest)

    # the string identifier
    string_id = models.CharField(max_length=100, editable=False, unique=True)

    # the inner xml of this response (used to extract the object quickly (ideally))
    xml = models.TextField(editable=False)

    def _create_children(self, resp_obj=None, response_dict={}):
        '''generate the database entries for the inputs to this response'''

        # see if we need to construct the object from database
        if resp_obj is None:
            resp_obj = self._make_capa()

        print response_dict

        # go through inputs in this response object
        for entry in resp_obj.inputfields:
            # create the input models
            Input.objects.create(
                response=self,
                string_id=entry.attrib['id'],
                answer=response_dict.get(entry.attrib['id'], ''))

    def _make_capa(self):
        '''get the capa-response object to which this response model corresponds'''
        parent_capa = self.content_test._make_capa()

        # the obvious way doesn't work :(
        # return parent_capa.responders[self.xml]

        self_capa = None
        for responder in parent_capa.responders.values():
            if responder.id == self.string_id:
                self_capa = responder
                break

        if self_capa is None:
            raise LookupError

        return self_capa


class Input(models.Model):
    '''the input to a Response'''

    # The response in which this input lives
    response = models.ForeignKey(Response)

    # sequence (first response field, second, etc)
    string_id = models.CharField(max_length=100, editable=False, unique=True)

    # the input, supposed a string
    answer = models.CharField(max_length=50, blank=True)
